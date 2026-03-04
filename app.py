"""
Technology Version Compliance & Obsolescence Management Tool
Local Streamlit application — runs entirely on the user's laptop.
"""
import os
import traceback

import polars as pl
import streamlit as st

from config import get_azure_config
from db.store import register, reset
from modules.cleaner import clean_device42, get_cleaning_stats
from modules.compliance import (
    build_compliance_summary,
    check_ea_gaps,
    flag_obsolete_technologies,
    flag_retired_still_tagged,
    get_records_with_gaps,
)
from modules.ingestion import load_asset_inventory, load_device42, load_ea_tool
from modules.mapper import (
    build_untagged_tech_mapping,
    map_hostnames_to_apps,
    summarise_app_tech_coverage,
)
from modules.matcher import match_technologies, results_to_dataframe
from modules.reporter import generate_report

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Tech Compliance Tool",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Session state init ────────────────────────────────────────────────────────

KEYS = [
    "device42_df",    # raw Device42 data
    "asset_df",       # filtered Asset Inventory
    "ea_sheets",      # dict[sheet_name, DataFrame] from EA Tool
    "cleaned_df",     # Device42 after cleaning pipeline
    "match_results",  # list[dict] from matcher
    "mapping_df",     # tech + application join
    "compliance_df",  # EA Tool with gap flags
]
for _k in KEYS:
    if _k not in st.session_state:
        st.session_state[_k] = None

# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("Tech Compliance")
    st.caption("Technology Version Compliance & Obsolescence Management")

    st.divider()

    # Azure AI config (pre-filled from .env if present)
    cfg = get_azure_config()
    st.subheader("Azure AI Configuration")
    azure_endpoint   = st.text_input("Endpoint",   value=cfg["endpoint"])
    azure_key        = st.text_input("API Key",     value=cfg["api_key"], type="password")
    azure_deployment = st.text_input("Deployment",  value=cfg["deployment"])

    ai_enabled = bool(azure_endpoint and azure_key)
    if ai_enabled:
        st.success("AI matching: Enabled")
    else:
        st.warning("AI matching: Disabled\n(fuzzy only — fill Endpoint + Key to enable)")

    # Push Azure config into env so modules can read it at call time
    if azure_endpoint:
        os.environ["AZURE_OPENAI_ENDPOINT"]   = azure_endpoint
    if azure_key:
        os.environ["AZURE_OPENAI_API_KEY"]    = azure_key
    if azure_deployment:
        os.environ["AZURE_OPENAI_DEPLOYMENT"] = azure_deployment

    st.divider()

    # Workflow progress
    st.subheader("Workflow Progress")
    steps = {
        "1. Upload Files":        st.session_state.device42_df is not None,
        "2. Clean Data":          st.session_state.cleaned_df is not None,
        "3. Match Technologies":  st.session_state.match_results is not None,
        "4. Map Applications":    st.session_state.mapping_df is not None,
        "5. Compliance Check":    st.session_state.compliance_df is not None,
    }
    for label, done in steps.items():
        st.write(("✅ " if done else "⏳ ") + label)

    st.divider()
    if st.button("Reset Session", type="secondary", use_container_width=True):
        for k in KEYS:
            st.session_state[k] = None
        reset()
        st.rerun()

# ── Tabs ──────────────────────────────────────────────────────────────────────

tabs = st.tabs([
    "📁 1. Upload Data",
    "🔧 2. Process & Clean",
    "🔍 3. Match Technologies",
    "🗺️ 4. Map Applications",
    "✅ 5. Compliance Check",
    "📊 6. Reports",
])

# ─────────────────────────────────────────────────────────────────────────────
# TAB 1 — Upload Data
# ─────────────────────────────────────────────────────────────────────────────
with tabs[0]:
    st.header("Upload Input Files")
    st.caption("Upload all three source files. Large files (3M rows) may take a minute to load.")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.subheader("Device42 / Infinity Feed")
        st.caption("Multi-tab Excel · Hostname, Software Name, Software Version")
        d42_file = st.file_uploader("Choose file", type=["xlsx", "xls"], key="up_d42")
        if d42_file:
            try:
                # Peek at sheet count first so progress bar is meaningful
                import pandas as _pd
                _xl = _pd.ExcelFile(d42_file)
                total_sheets = len(_xl.sheet_names)
                d42_file.seek(0)  # reset pointer after peek

                progress_bar = st.progress(0, text="Reading sheet 1 of 0...")
                status_text  = st.empty()

                def d42_progress(current, total, sheet_name, rows_so_far):
                    pct  = int(current / max(total, 1) * 100)
                    text = (
                        f"Reading tab **{current}/{total}** — `{sheet_name}` "
                        f"({rows_so_far:,} rows loaded so far)  {pct}%"
                    )
                    progress_bar.progress(pct / 100, text=f"{pct}% — tab {current}/{total}: {sheet_name}")
                    status_text.caption(text)

                st.session_state.device42_df = load_device42(d42_file, progress_callback=d42_progress)
                progress_bar.empty()
                status_text.empty()

                count = len(st.session_state.device42_df)
                st.success(f"Loaded **{count:,}** records across {total_sheets} tab(s)")
                st.dataframe(st.session_state.device42_df.head(5).to_pandas(), use_container_width=True)
            except Exception as e:
                st.error(str(e))

    with col2:
        st.subheader("Asset Inventory")
        st.caption("Filtered to SG/MY, PROD/DR, LIVE · Hostname → Application")
        asset_file = st.file_uploader("Choose file", type=["xlsx", "xls"], key="up_asset")
        if asset_file:
            with st.spinner("Loading Asset Inventory..."):
                try:
                    st.session_state.asset_df = load_asset_inventory(asset_file)
                    count = len(st.session_state.asset_df)
                    st.success(f"Loaded **{count:,}** records after scope filter")
                    st.dataframe(st.session_state.asset_df.head(5).to_pandas(), use_container_width=True)
                except Exception as e:
                    st.error(str(e))

    with col3:
        st.subheader("EA Tool Export")
        st.caption("HOPEX / TA Export · can have multiple sheets")
        ea_file = st.file_uploader("Choose file", type=["xlsx", "xls"], key="up_ea")
        if ea_file:
            with st.spinner("Loading EA Tool..."):
                try:
                    st.session_state.ea_sheets = load_ea_tool(ea_file)
                    names = list(st.session_state.ea_sheets.keys())
                    st.success(f"Loaded **{len(names)}** sheet(s): {', '.join(names)}")
                    selected = st.selectbox("Preview sheet", names, key="ea_preview")
                    st.dataframe(
                        st.session_state.ea_sheets[selected].head(5).to_pandas(),
                        use_container_width=True,
                    )
                except Exception as e:
                    st.error(str(e))

# ─────────────────────────────────────────────────────────────────────────────
# TAB 2 — Process & Clean
# ─────────────────────────────────────────────────────────────────────────────
with tabs[1]:
    st.header("Process & Clean Device42 Data")

    if st.session_state.device42_df is None:
        st.info("Upload the Device42 file in Step 1 first.")
    else:
        raw_df = st.session_state.device42_df
        st.metric("Raw records loaded", f"{len(raw_df):,}")

        st.markdown(
            "The pipeline will:\n"
            "- Keep only hostnames starting with **P** or **D**\n"
            "- Remove KB patches, hotfixes, security/cumulative updates\n"
            "- Deduplicate rows\n"
            "- Add a normalised `tech_key` (name + version, lowercase)"
        )

        if st.button("Run Cleaning Pipeline", type="primary"):
            with st.spinner("Cleaning data..."):
                try:
                    cleaned = clean_device42(raw_df)
                    st.session_state.cleaned_df = cleaned
                    register("device42_clean", cleaned)
                    stats = get_cleaning_stats(raw_df, cleaned)

                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("After Cleaning",    f"{stats['cleaned_records']:,}")
                    c2.metric("Removed",           f"{stats['removed']:,}  ({stats['removal_pct']}%)")
                    c3.metric("Unique Hostnames",   f"{stats['unique_hostnames']:,}")
                    c4.metric("Unique Technologies", f"{stats['unique_technologies']:,}")
                    st.success("Cleaning complete.")
                except Exception as e:
                    st.error(str(e))
                    st.code(traceback.format_exc())

        if st.session_state.cleaned_df is not None:
            with st.expander("Preview cleaned data (first 200 rows)"):
                st.dataframe(
                    st.session_state.cleaned_df.head(200).to_pandas(),
                    use_container_width=True,
                )

# ─────────────────────────────────────────────────────────────────────────────
# TAB 3 — Match Technologies
# ─────────────────────────────────────────────────────────────────────────────
with tabs[2]:
    st.header("Match Technologies: Device42 ↔ EA Tool")
    st.caption(
        "Matching runs on **unique** technology names only (not all 3M rows). "
        "Tiers: Exact → Fuzzy (RapidFuzz) → AI (Azure OpenAI for ambiguous cases)."
    )

    if st.session_state.cleaned_df is None:
        st.info("Complete Step 2 (Clean Data) first.")
    elif st.session_state.ea_sheets is None:
        st.info("Upload the EA Tool file in Step 1 first.")
    else:
        ea_sheets = st.session_state.ea_sheets

        col_a, col_b = st.columns(2)
        with col_a:
            ea_sheet = st.selectbox(
                "EA Tool sheet containing technology list",
                list(ea_sheets.keys()),
                key="match_ea_sheet",
            )
        with col_b:
            ea_df_for_match = ea_sheets[ea_sheet]
            ea_tech_col = st.selectbox(
                "Technology name column in that sheet",
                ea_df_for_match.columns,
                key="match_tech_col",
            )

        unique_d42   = st.session_state.cleaned_df["software_name"].n_unique()
        unique_ea    = ea_df_for_match[ea_tech_col].n_unique()

        m1, m2, m3 = st.columns(3)
        m1.metric("Device42 unique techs", f"{unique_d42:,}")
        m2.metric("EA Tool unique techs",  f"{unique_ea:,}")
        m3.metric("AI matching",           "Enabled" if ai_enabled else "Disabled")

        if st.button("Run Matching Engine", type="primary"):
            source_techs = st.session_state.cleaned_df["software_name"].unique().to_list()
            ea_techs     = ea_df_for_match[ea_tech_col].drop_nulls().unique().to_list()

            progress_bar = st.progress(0, text="Starting matching...")

            def _progress(current, total):
                pct  = current / total
                text = f"Matching {current:,} / {total:,} technologies..."
                progress_bar.progress(pct, text=text)

            with st.spinner("Running matching engine — this may take a few minutes for large sets..."):
                try:
                    results = match_technologies(source_techs, ea_techs, _progress)
                    st.session_state.match_results = results
                    progress_bar.empty()
                    matched_n = sum(1 for r in results if r["matched"])
                    st.success(
                        f"Matching complete — **{matched_n:,}** / **{len(results):,}** matched "
                        f"({matched_n / max(len(results), 1) * 100:.1f}%)"
                    )
                except Exception as e:
                    progress_bar.empty()
                    st.error(str(e))
                    st.code(traceback.format_exc())

        if st.session_state.match_results:
            results  = st.session_state.match_results
            df_res   = results_to_dataframe(results)
            matched  = df_res.filter(pl.col("matched") == True)
            unmatched = df_res.filter(pl.col("matched") == False)

            r1, r2, r3, r4, r5 = st.columns(5)
            r1.metric("Total",     f"{len(results):,}")
            r2.metric("Exact",     f"{df_res.filter(pl.col('match_type') == 'exact').height:,}")
            r3.metric("Fuzzy",     f"{df_res.filter(pl.col('match_type') == 'fuzzy').height:,}")
            r4.metric("AI",        f"{df_res.filter(pl.col('match_type') == 'ai').height:,}")
            r5.metric("Unmatched", f"{len(unmatched):,}")

            tab_a, tab_b = st.tabs(["Unmatched — requires human review", "All results"])
            with tab_a:
                st.dataframe(unmatched.to_pandas(), use_container_width=True, height=400)
            with tab_b:
                st.dataframe(df_res.to_pandas(), use_container_width=True, height=400)

# ─────────────────────────────────────────────────────────────────────────────
# TAB 4 — Map Applications
# ─────────────────────────────────────────────────────────────────────────────
with tabs[3]:
    st.header("Map Technologies to Applications")

    if st.session_state.cleaned_df is None or st.session_state.asset_df is None:
        st.info("Complete Steps 1–2 (Upload + Clean) first.")
    else:
        # ── Section A: Full tech → app mapping ──────────────────────────────
        st.subheader("A. Full Technology → Application Mapping")
        st.caption("Joins all cleaned Device42 records to Asset Inventory by hostname.")

        if st.button("Build Full Mapping", type="primary"):
            with st.spinner("Building mapping..."):
                try:
                    mapping = map_hostnames_to_apps(
                        st.session_state.cleaned_df,
                        st.session_state.asset_df,
                    )
                    st.session_state.mapping_df = mapping
                    register("tech_app_mapping", mapping)

                    total     = len(mapping)
                    app_col   = "application_name" if "application_name" in mapping.columns else None
                    mapped_n  = mapping.filter(pl.col(app_col) != "").height if app_col else 0
                    unmapped  = total - mapped_n

                    c1, c2, c3 = st.columns(3)
                    c1.metric("Total Records",     f"{total:,}")
                    c2.metric("Mapped to App",     f"{mapped_n:,}")
                    c3.metric("No App Found",      f"{unmapped:,}")
                    st.success("Mapping complete.")
                except Exception as e:
                    st.error(str(e))
                    st.code(traceback.format_exc())

        if st.session_state.mapping_df is not None:
            with st.expander("Preview mapping (first 200 rows)"):
                st.dataframe(
                    st.session_state.mapping_df.head(200).to_pandas(),
                    use_container_width=True,
                )
            with st.expander("Technologies per application (top 50)"):
                summary = summarise_app_tech_coverage(st.session_state.mapping_df)
                st.dataframe(summary.head(50).to_pandas(), use_container_width=True)

        st.divider()

        # ── Section B: Untagged EA technologies → find owning application ───
        st.subheader("B. Find Applications for EA Untagged Technologies")
        st.caption(
            "Select the EA Tool sheet that lists technologies **not tagged to any application**. "
            "The tool will find which hostnames use them and which application owns those hostnames."
        )

        if st.session_state.ea_sheets is None:
            st.info("Upload the EA Tool file in Step 1 first.")
        else:
            ea_sheets = st.session_state.ea_sheets
            col_x, col_y = st.columns(2)
            with col_x:
                untagged_sheet = st.selectbox(
                    "EA sheet with untagged technologies",
                    list(ea_sheets.keys()),
                    key="untagged_sheet",
                )
            with col_y:
                untagged_col = st.selectbox(
                    "Technology name column",
                    ea_sheets[untagged_sheet].columns,
                    key="untagged_col",
                )

            if st.button("Find Owning Applications", type="secondary"):
                untagged_techs = (
                    ea_sheets[untagged_sheet][untagged_col]
                    .drop_nulls()
                    .to_list()
                )
                with st.spinner("Looking up applications..."):
                    try:
                        untagged_map = build_untagged_tech_mapping(
                            untagged_techs,
                            st.session_state.cleaned_df,
                            st.session_state.asset_df,
                        )
                        st.session_state["untagged_map"] = untagged_map
                        st.success(f"Found **{len(untagged_map):,}** hostname-technology records.")
                        st.dataframe(untagged_map.to_pandas(), use_container_width=True, height=400)
                    except Exception as e:
                        st.error(str(e))
                        st.code(traceback.format_exc())

# ─────────────────────────────────────────────────────────────────────────────
# TAB 5 — Compliance Check
# ─────────────────────────────────────────────────────────────────────────────
with tabs[4]:
    st.header("Compliance & EA Gap Analysis")
    st.caption(
        "Scans the EA Tool export for missing governance fields "
        "(RCSA, owner, upgrade plan, etc.) and obsolete technologies."
    )

    if st.session_state.ea_sheets is None:
        st.info("Upload the EA Tool file in Step 1 first.")
    else:
        ea_sheets = st.session_state.ea_sheets
        comp_sheet = st.selectbox(
            "Select EA Tool sheet for compliance check",
            list(ea_sheets.keys()),
            key="comp_sheet",
        )

        if st.button("Run Compliance Check", type="primary"):
            ea_df = ea_sheets[comp_sheet]
            with st.spinner("Checking compliance gaps..."):
                try:
                    result = check_ea_gaps(ea_df)
                    result = flag_obsolete_technologies(result)
                    result = flag_retired_still_tagged(result)
                    st.session_state.compliance_df = result
                    st.success("Compliance check complete.")
                except Exception as e:
                    st.error(str(e))
                    st.code(traceback.format_exc())

        if st.session_state.compliance_df is not None:
            comp_df  = st.session_state.compliance_df
            summary  = build_compliance_summary(comp_df)
            gap_recs = get_records_with_gaps(comp_df)

            # Metrics row
            metric_cols = st.columns(min(len(summary), 6))
            for i, (label, val) in enumerate(summary.items()):
                metric_cols[i % len(metric_cols)].metric(label, f"{val:,}")

            st.divider()

            tab_gaps, tab_obsolete, tab_all = st.tabs([
                "Records with Gaps",
                "Obsolete / Retired Technologies",
                "Full EA Data",
            ])

            with tab_gaps:
                st.caption(f"{len(gap_recs):,} records have at least one gap or flag.")
                st.dataframe(gap_recs.to_pandas(), use_container_width=True, height=450)

            with tab_obsolete:
                if "is_obsolete" in comp_df.columns:
                    obs_df = comp_df.filter(pl.col("is_obsolete") == True)
                    st.caption(f"{len(obs_df):,} obsolete/end-of-life technologies.")
                    st.dataframe(obs_df.to_pandas(), use_container_width=True, height=450)
                else:
                    st.info("No lifecycle status column detected in this EA sheet.")

            with tab_all:
                st.dataframe(comp_df.to_pandas(), use_container_width=True, height=450)

# ─────────────────────────────────────────────────────────────────────────────
# TAB 6 — Reports
# ─────────────────────────────────────────────────────────────────────────────
with tabs[5]:
    st.header("Download Reports")
    st.caption("Generates a single formatted Excel workbook with all available result sheets.")

    # Collect available output sheets
    report_sheets: dict[str, pl.DataFrame] = {}

    if st.session_state.cleaned_df is not None:
        report_sheets["Tech Recon"] = st.session_state.cleaned_df
    if st.session_state.mapping_df is not None:
        report_sheets["App Mapping"] = st.session_state.mapping_df
    if st.session_state.compliance_df is not None:
        report_sheets["Compliance Gaps"] = st.session_state.compliance_df
    if st.session_state.match_results:
        report_sheets["Match Results"] = results_to_dataframe(st.session_state.match_results)
    if st.session_state.get("untagged_map") is not None:
        report_sheets["Untagged Tech Mapping"] = st.session_state["untagged_map"]

    if not report_sheets:
        st.info("Complete the workflow steps (2–5) to generate reports.")
    else:
        st.write(f"**{len(report_sheets)} sheet(s)** ready to export:")
        for name, df in report_sheets.items():
            st.write(f"  - **{name}**: {len(df):,} rows × {len(df.columns)} columns")

        st.divider()

        if st.button("Generate Excel Report", type="primary"):
            with st.spinner("Building Excel workbook..."):
                try:
                    report_bytes = generate_report(report_sheets)
                    st.download_button(
                        label="⬇️  Download tech_compliance_report.xlsx",
                        data=report_bytes,
                        file_name="tech_compliance_report.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True,
                    )
                except Exception as e:
                    st.error(str(e))
                    st.code(traceback.format_exc())
