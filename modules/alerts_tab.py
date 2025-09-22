# filepath: d:\Portfolio Dashboard Project\portfolio_dashboard\modules\alerts_tab.py
import os
import json
from pathlib import Path
import streamlit as st
import pandas as pd
from utils.alerts import generate_alerts

PL_COMP_OPTS = ["Greater Than", "Less Than", "Range"]
MAX_INV_PCT = 0.10  # 10% cap used for headline investment info
ALERT_RULES_PATH = Path("data/alert_rules.json")


# ------------- Persistence Helpers -------------
def _ensure_rules_dir():
    ALERT_RULES_PATH.parent.mkdir(parents=True, exist_ok=True)


def _load_rules_from_disk():
    if ALERT_RULES_PATH.exists():
        try:
            with open(ALERT_RULES_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                # Basic sanity filter
                clean = []
                for r in data:
                    if isinstance(r, dict):
                        clean.append(r)
                return clean
        except Exception:
            pass
    return []


def _save_rules_to_disk(rules: list):
    _ensure_rules_dir()
    try:
        with open(ALERT_RULES_PATH, "w", encoding="utf-8") as f:
            json.dump(rules, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# --------- State Initialization ---------
def init_alert_rules_state():
    ss = st.session_state
    first_time = "alert_rules" not in ss
    ss.setdefault("alert_rules", [])
    ss.setdefault("next_rule_id", 1)
    ss.setdefault("show_alert_rules_dialog", False)
    ss.setdefault("editing_rule_id", None)     # existing rule id OR "NEW" for draft
    ss.setdefault("rule_draft", None)          # holds unsaved new rule
    ss.setdefault("show_saved_toast", False)

    if first_time:
        loaded = _load_rules_from_disk()
        if loaded:
            ss.alert_rules = loaded
            # Derive next id
            try:
                ss.next_rule_id = max((r.get("id") or 0) for r in loaded) + 1
            except ValueError:
                ss.next_rule_id = 1


# --------- CRUD Helpers ---------
def _new_rule_template(next_id: int):
    return {
        "id": next_id,
        "name": "",
        "applied_to": [],
        "uni_common": "Unique",
        "common_in": [],
        "profit_loss": "",
        "pl_comp": "",
        "pl_from": 0.0,
        "pl_to": 0.0,
        "inv_comp": "",
        "inv_from": 0.0,
        "inv_to": 0.0,
        "inv_level": "Per Stock",  # investment evaluation level
        "message": ""
    }


def start_add_rule():
    ss = st.session_state
    if ss.rule_draft is None:
        ss.rule_draft = _new_rule_template(ss.next_rule_id)
    ss.editing_rule_id = "NEW"
    ss.show_alert_rules_dialog = True
    st.rerun()


def add_rule_finalize():
    ss = st.session_state
    if ss.rule_draft:
        rid = ss.next_rule_id
        draft = ss.rule_draft
        draft["id"] = rid
        ss.alert_rules.append(draft)
        ss.next_rule_id += 1
        _save_rules_to_disk(ss.alert_rules)
    ss.rule_draft = None
    ss.editing_rule_id = None
    ss.show_alert_rules_dialog = True
    ss.show_saved_toast = True
    st.rerun()


def delete_rule(rid: int):
    ss = st.session_state
    ss.alert_rules = [r for r in ss.alert_rules if r.get("id") != rid]
    _save_rules_to_disk(ss.alert_rules)
    if ss.editing_rule_id == rid:
        ss.editing_rule_id = None
    ss.show_alert_rules_dialog = True
    st.rerun()


def reset_rules():
    ss = st.session_state
    ss.alert_rules = []
    ss.next_rule_id = 1
    ss.editing_rule_id = None
    ss.rule_draft = None
    _save_rules_to_disk(ss.alert_rules)
    st.rerun()


def save_existing_rule(rid: int):
    ss = st.session_state
    for r in ss.alert_rules:
        if r.get("id") == rid:
            r["name"] = ss.get(f"rule_name_{rid}", r.get("name"))
            r["applied_to"] = ss.get(f"rule_applied_{rid}", r.get("applied_to", []))
            r["uni_common"] = ss.get(f"rule_uni_common_{rid}", r.get("uni_common", "Unique"))
            r["common_in"] = ss.get(f"rule_common_in_{rid}", r.get("common_in", []))
            r["profit_loss"] = ss.get(f"rule_profit_loss_{rid}", r.get("profit_loss", ""))
            r["pl_comp"] = ss.get(f"rule_pl_comp_{rid}", r.get("pl_comp", ""))
            r["pl_from"] = ss.get(f"rule_pl_from_{rid}", r.get("pl_from", 0.0))
            r["pl_to"] = ss.get(f"rule_pl_to_{rid}", r.get("pl_to", 0.0))
            r["inv_comp"] = ss.get(f"rule_inv_comp_{rid}", r.get("inv_comp", ""))
            r["inv_from"] = ss.get(f"rule_inv_from_{rid}", r.get("inv_from", 0.0))
            r["inv_to"] = ss.get(f"rule_inv_to_{rid}", r.get("inv_to", 0.0))
            r["inv_level"] = ss.get(f"rule_inv_level_{rid}", r.get("inv_level", "Per Stock"))
            r["message"] = ss.get(f"rule_message_{rid}", r.get("message", ""))
            break
    _save_rules_to_disk(ss.alert_rules)
    ss.editing_rule_id = None
    ss.show_alert_rules_dialog = True
    ss.show_saved_toast = True
    st.rerun()


def cancel_edit():
    ss = st.session_state
    if ss.editing_rule_id == "NEW":
        ss.rule_draft = None
    ss.editing_rule_id = None
    ss.show_alert_rules_dialog = True
    st.rerun()


# --------- Form Helpers ---------
def _capture_form_inputs(prefix_id, rule_obj, portfolios):
    rid = prefix_id
    st.text_input("Alert Name", value=rule_obj.get("name", ""), key=f"rule_name_{rid}", placeholder="Name")

    st.markdown("**1. Applied To**")
    all_ports = st.checkbox(
        "All Portfolios",
        key=f"rule_all_{rid}",
        value=(not rule_obj.get("applied_to"))
    )
    if all_ports:
        st.session_state[f"rule_applied_{rid}"] = []
        applied_display = portfolios
    else:
        st.multiselect(
            "Select Portfolios",
            portfolios,
            default=rule_obj.get("applied_to", []),
            key=f"rule_applied_{rid}"
        )
        applied_display = st.session_state.get(f"rule_applied_{rid}", [])

    st.markdown("**2. Scope**")
    st.radio(
        "Unique / Common",
        ["Unique", "Common"],
        key=f"rule_uni_common_{rid}",
        index=0 if rule_obj.get("uni_common") == "Unique" else 1,
        horizontal=True
    )
    mode = st.session_state[f"rule_uni_common_{rid}"]
    if mode == "Common":
        subset = applied_display if applied_display else portfolios
        st.multiselect(
            "Common Across (subset)",
            subset,
            default=rule_obj.get("common_in") if rule_obj.get("common_in") else subset,
            key=f"rule_common_in_{rid}"
        )
    else:
        st.session_state[f"rule_common_in_{rid}"] = []

    st.markdown("**3. Profit / Loss**")
    dir_opts = ["Profit", "Loss", "Unchanged"]
    cur_dir = rule_obj.get("profit_loss", "")
    idx_dir = dir_opts.index(cur_dir) + 1 if cur_dir in dir_opts else 0
    direction = st.selectbox(
        "Direction",
        [""] + dir_opts,
        index=idx_dir,
        key=f"rule_profit_loss_{rid}",
        format_func=lambda v: "Select direction" if v == "" else v
    )

    if direction and direction != "Unchanged":
        comp_opts = PL_COMP_OPTS
        cur_comp = rule_obj.get("pl_comp", "")
        idx_comp = comp_opts.index(cur_comp) + 1 if cur_comp in comp_opts else 0
        comp = st.selectbox(
            "Comparator",
            [""] + comp_opts,
            index=idx_comp,
            key=f"rule_pl_comp_{rid}",
            format_func=lambda v: "Select comparator" if v == "" else v
        )
        if comp == "Range":
            c1, c2 = st.columns(2)
            with c1:
                st.number_input("From (%)", value=rule_obj.get("pl_from", 0.0), step=0.5, key=f"rule_pl_from_{rid}")
            with c2:
                st.number_input("To (%)", value=rule_obj.get("pl_to", 0.0), step=0.5, key=f"rule_pl_to_{rid}")
        elif comp in ("Greater Than", "Less Than"):
            st.number_input("Value (%)", value=rule_obj.get("pl_from", 0.0), step=0.5, key=f"rule_pl_from_{rid}")

    st.markdown("**4. Investment Filter**")
    st.radio(
        "Investment Scope",
        ["Per Portfolio", "Per Stock"],
        key=f"rule_inv_level_{rid}",
        index=0 if rule_obj.get("inv_level") == "Per Portfolio" else 1,
        horizontal=True,
        help="Per Portfolio: filter by total capital of each portfolio.\nPer Stock: filter by capital in each stock."
    )
    inv_opts = PL_COMP_OPTS
    cur_inv = rule_obj.get("inv_comp", "")
    idx_inv = inv_opts.index(cur_inv) + 1 if cur_inv in inv_opts else 0
    inv_comp = st.selectbox(
        "Investment Comparator",
        [""] + inv_opts,
        index=idx_inv,
        key=f"rule_inv_comp_{rid}",
        format_func=lambda v: "Select comparator" if v == "" else v
    )
    if inv_comp == "Range":
        c3, c4 = st.columns(2)
        with c3:
            st.number_input(
                "Investment From (₹)",
                value=float(rule_obj.get("inv_from", 0.0)),
                step=5000.0,
                key=f"rule_inv_from_{rid}"
            )
        with c4:
            st.number_input(
                "Investment To (₹)",
                value=float(rule_obj.get("inv_to", 0.0)),
                step=5000.0,
                key=f"rule_inv_to_{rid}"
            )
    elif inv_comp in ("Greater Than", "Less Than"):
        st.number_input(
            "Investment Value (₹)",
            value=float(rule_obj.get("inv_from", 0.0)),
            step=5000.0,
            key=f"rule_inv_from_{rid}"
        )

    st.markdown("**5. Message**")
    st.text_area(
        "Message",
        value=rule_obj.get("message", ""),
        key=f"rule_message_{rid}",
        height=70,
        placeholder="Short alert message"
    )


def _draft_from_session(r):
    rid = "NEW"
    return {
        "id": r["id"],
        "name": st.session_state.get(f"rule_name_{rid}", r.get("name", "")),
        "applied_to": st.session_state.get(f"rule_applied_{rid}", r.get("applied_to", [])),
        "uni_common": st.session_state.get(f"rule_uni_common_{rid}", r.get("uni_common", "Unique")),
        "common_in": st.session_state.get(f"rule_common_in_{rid}", r.get("common_in", [])),
        "profit_loss": st.session_state.get(f"rule_profit_loss_{rid}", r.get("profit_loss", "")),
        "pl_comp": st.session_state.get(f"rule_pl_comp_{rid}", r.get("pl_comp", "")),
        "pl_from": st.session_state.get(f"rule_pl_from_{rid}", r.get("pl_from", 0.0)),
        "pl_to": st.session_state.get(f"rule_pl_to_{rid}", r.get("pl_to", 0.0)),
        "inv_comp": st.session_state.get(f"rule_inv_comp_{rid}", r.get("inv_comp", "")),
        "inv_from": st.session_state.get(f"rule_inv_from_{rid}", r.get("inv_from", 0.0)),
        "inv_to": st.session_state.get(f"rule_inv_to_{rid}", r.get("inv_to", 0.0)),
        "inv_level": st.session_state.get(f"rule_inv_level_{rid}", r.get("inv_level", "Per Stock")),
        "message": st.session_state.get(f"rule_message_{rid}", r.get("message", ""))
    }


# --------- Dialog Rendering ---------
def _rules_list_body():
    st.markdown("### Alert Rules")
    cR, cC = st.columns([0.5, 0.5])
    with cR:
        st.button("Reset (Delete All)", on_click=reset_rules, type="secondary", use_container_width=True)
    with cC:
        st.button("Close", on_click=cancel_edit, use_container_width=True)

    st.divider()
    if not st.session_state.alert_rules:
        st.info("No saved rules yet.")
        return
    for r in sorted(st.session_state.alert_rules, key=lambda x: x["id"]):
        cols = st.columns([0.55, 0.20, 0.25])
        with cols[0]:
            st.write(r.get("name") or f"(Unnamed #{r.get('id')})")
        with cols[1]:
            if st.button("✏️ Edit", key=f"edit_{r.get('id')}"):
                st.session_state.editing_rule_id = r.get("id")
                st.rerun()
        with cols[2]:
            if st.button("🗑️", key=f"del_{r.get('id')}"):
                delete_rule(r.get("id"))


def _render_edit(portfolios):
    ss = st.session_state
    is_new = (ss.editing_rule_id == "NEW")
    rule_obj = ss.rule_draft if is_new else next(
        (r for r in ss.alert_rules if r.get("id") == ss.editing_rule_id), None
    )
    if not rule_obj:
        st.warning("Rule not found.")
        return
    st.markdown(f"### {'New Rule' if is_new else f'Edit Rule (ID {rule_obj['id']})'}")
    st.button("← Back to List", on_click=lambda: ss.update(editing_rule_id=None), type="secondary")
    st.divider()
    prefix = "NEW" if is_new else rule_obj["id"]
    _capture_form_inputs(prefix, rule_obj, portfolios)

    cols = st.columns([0.5, 0.25, 0.25])
    with cols[1]:
        if st.button("Save", key=f"save_rule_{prefix}"):
            if is_new:
                ss.rule_draft = _draft_from_session(rule_obj)
                add_rule_finalize()
            else:
                save_existing_rule(rule_obj["id"])
    with cols[2]:
        st.button("Cancel", key=f"cancel_rule_{prefix}", on_click=cancel_edit)


def render_rules_dialog(valid_dfs):
    if not st.session_state.get("show_alert_rules_dialog"):
        return
    portfolios = list(valid_dfs.keys())
    if st.session_state.editing_rule_id == "NEW" and st.session_state.rule_draft is None:
        st.session_state.rule_draft = _new_rule_template(st.session_state.next_rule_id)

    def _body():
        if st.session_state.editing_rule_id in (None,):
            _rules_list_body()
        elif st.session_state.editing_rule_id == "NEW":
            _render_edit(portfolios)
        else:
            _render_edit(portfolios)

    if hasattr(st, "dialog"):
        @st.dialog("Set Alert Rules")
        def _dlg():
            if st.session_state.editing_rule_id is None:
                _rules_list_body()
            else:
                _body()
        _dlg()
    else:
        with st.expander("Set Alert Rules", expanded=True):
            _body()


# --------- Public Tab Renderer ---------
def render_alerts_tab(valid_dfs):
    init_alert_rules_state()
    ss = st.session_state

    opened_this_run = False
    col_add, col_settings = st.columns([0.15, 0.15])
    with col_add:
        if st.button("➕ Add Rule", key="add_rule_btn"):
            start_add_rule()
            opened_this_run = True
    with col_settings:
        if ss.alert_rules:
            if st.button("⚙️ Settings", key="alert_settings_btn"):
                ss.show_alert_rules_dialog = True
                ss.editing_rule_id = None
                opened_this_run = True

    if ss.show_alert_rules_dialog and not opened_this_run and ss.editing_rule_id is None:
        ss.show_alert_rules_dialog = False

    if not ss.alert_rules and ss.rule_draft is None:
        st.info("No alert rules configured. Click Add Rule to create one.")
    else:
        if not valid_dfs:
            st.warning("No portfolios loaded to evaluate alerts.")
        else:
            alerts_df = generate_alerts(valid_dfs, ss.alert_rules)
            if alerts_df.empty:
                st.info("No alerts triggered for current rules.")
            else:
                mode = st.radio(
                    "View Mode",
                    ["By Portfolio", "By Rule"],
                    horizontal=True,
                    key="alerts_view_mode"
                )
                if mode == "By Portfolio":
                    port = st.selectbox(
                        "Select Portfolio",
                        sorted(alerts_df["portfolio"].unique()),
                        key="alerts_port_pick"
                    )
                    subset = alerts_df[alerts_df["portfolio"] == port]
                else:
                    rule = st.selectbox(
                        "Select Rule",
                        sorted(alerts_df["rule"].unique()),
                        key="alerts_rule_pick"
                    )
                    subset = alerts_df[alerts_df["rule"] == rule]

                if subset.empty:
                    st.warning("No matches for selection.")
                else:
                    instruments = [
                        i for i in subset["instrument"].unique()
                        if i and i != "(Portfolio Total)"
                    ]
                    instruments.sort()

                    for instr in instruments:
                        instr_alert_rows = subset[subset["instrument"] == instr]
                        rule_names = sorted(instr_alert_rows["rule"].unique())
                        rules_str = ", ".join(rule_names)

                        # Presence determination
                        present_ports = []
                        for p, dfp in valid_dfs.items():
                            if dfp is not None and not dfp.empty and "instrument" in dfp.columns:
                                if instr in dfp["instrument"].values:
                                    present_ports.append(p)
                        all_ports_list = list(valid_dfs.keys())
                        absent_ports = [p for p in all_ports_list if p not in present_ports]

                        # Build styled headline parts (HTML)
                        headline_parts_html = []
                        for p in present_ports:
                            dfp = valid_dfs.get(p)
                            if dfp is None or dfp.empty:
                                continue
                            if "invested" not in dfp.columns and {"quantity", "avg_price"}.issubset(dfp.columns):
                                df_loc = dfp.copy()
                                df_loc["invested"] = df_loc["quantity"] * df_loc["avg_price"]
                            else:
                                df_loc = dfp
                            if "invested" not in df_loc.columns:
                                continue
                            total_cap = float(df_loc["invested"].sum())
                            max_inv = total_cap * MAX_INV_PCT if total_cap > 0 else 0.0
                            cur_inv = float(df_loc.loc[df_loc["instrument"] == instr, "invested"].sum())
                            exceed = (max_inv > 0) and (cur_inv > max_inv)
                            remaining = max_inv - cur_inv

                            if exceed:
                                part_html = (
                                    f"<span style='color:#c00;font-weight:600'>"
                                    f"{p}: Curr ₹{cur_inv:,.0f}! / Max ₹{max_inv:,.0f} / Rem: EXCEEDED {int(MAX_INV_PCT*100)}% limit"
                                    f"</span>"
                                )
                            else:
                                part_html = (
                                    f"<span style='color:#444'>"
                                    f"{p}: Curr ₹{cur_inv:,.0f} / Max ₹{max_inv:,.0f} / Rem: ₹{remaining:,.0f}"
                                    f"</span>"
                                )
                            headline_parts_html.append(part_html)

                        inv_headline_html = " | ".join(headline_parts_html) if headline_parts_html else "<span style='color:#666'>No investment data</span>"

                        summary_html = (
                            f"<summary style='cursor:pointer;'>"
                            f"<b>{instr}</b> | {inv_headline_html} | "
                            f"<span style='color:#555'>Rules: {rules_str}</span>"
                            f"</summary>"
                        )

                        # Build detail rows
                        detail_rows = []
                        for p in present_ports:
                            dfp = valid_dfs.get(p)
                            if dfp is None or dfp.empty:
                                continue
                            if "invested" not in dfp.columns and {"quantity", "avg_price"}.issubset(dfp.columns):
                                df_tmp = dfp.copy()
                                df_tmp["invested"] = df_tmp["quantity"] * df_tmp["avg_price"]
                            else:
                                df_tmp = dfp

                            row_match = df_tmp[df_tmp["instrument"] == instr]
                            if row_match.empty:
                                continue
                            row0 = row_match.iloc[0]
                            avg_price = float(row0.get("avg_price", 0) or 0)

                            curr_price = None
                            for col in ("ltp", "current_price", "last_price", "close"):
                                if col in row0 and pd.notna(row0[col]):
                                    curr_price = float(row0[col])
                                    break
                            pnl_pct = row0.get("pnl_pct", None)
                            if curr_price is None and pnl_pct is not None and avg_price:
                                try:
                                    curr_price = avg_price * (1 + float(pnl_pct) / 100.0)
                                except Exception:
                                    pass
                            if curr_price is None:
                                curr_price = avg_price
                            if pnl_pct is None or pd.isna(pnl_pct):
                                if avg_price:
                                    pnl_pct = ((curr_price - avg_price) / avg_price) * 100.0
                                else:
                                    pnl_pct = 0.0

                            detail_rows.append({
                                "Portfolio": p,
                                "Avg Price": round(avg_price, 2),
                                "Current Price": round(curr_price, 2),
                                "% Change": round(float(pnl_pct), 2)
                            })

                        if detail_rows:
                            df_detail = pd.DataFrame(detail_rows)
                            avg_pct = round(df_detail["% Change"].mean(), 2)
                            df_detail = pd.concat([
                                df_detail,
                                pd.DataFrame([{
                                    "Portfolio": "Average",
                                    "Avg Price": "",
                                    "Current Price": "",
                                    "% Change": avg_pct
                                }])
                            ], ignore_index=True)
                            df_display = df_detail.copy()
                            df_display["% Change"] = df_display["% Change"].apply(
                                lambda v: v if v == "" else f"{v:.2f}%"
                            )
                            table_html = df_display.to_html(index=False, justify="center")
                        else:
                            table_html = "<em style='color:#666'>No detailed data available.</em>"

                        # Alert messages
                        alerts_html = ""
                        if len(instr_alert_rows) > 0:
                            msgs = "".join(
                                f"<li><b>{arow['rule']}</b>: {arow['message']}</li>"
                                for _, arow in instr_alert_rows.iterrows()
                            )
                            alerts_html = f"<ul style='margin:4px 0 0 18px;padding:0'>{msgs}</ul>"

                        presence_html = (
                            f"<div style='font-size:0.7rem;color:#555;margin-top:4px;'>"
                            f"Present in: {', '.join(present_ports) if present_ports else 'None'} | "
                            f"Not in: {', '.join(absent_ports) if absent_ports else 'None'}"
                            f"</div>"
                        )

                        block_html = (
                            "<details style='border:1px solid #ddd;border-radius:6px;padding:6px 10px;"
                            "background:#f9f9f9;margin-bottom:8px;'>"
                            f"{summary_html}"
                            f"{presence_html}"
                            f"<div style='margin-top:6px'>{table_html}</div>"
                            f"{alerts_html}"
                            "</details>"
                        )

                        st.markdown(block_html, unsafe_allow_html=True)

    if ss.get("show_saved_toast"):
        st.toast("Rule saved")
        ss.show_saved_toast = False

    render_rules_dialog(valid_dfs)
