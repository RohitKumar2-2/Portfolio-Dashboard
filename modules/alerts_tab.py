
import streamlit as st
from utils.alerts import generate_alerts

PL_COMP_OPTS = ["Greater Than", "Less Than", "Range"]

# --------- State Initialization ---------
def init_alert_rules_state():
    ss = st.session_state
    ss.setdefault("alert_rules", [])
    ss.setdefault("next_rule_id", 1)
    ss.setdefault("show_alert_rules_dialog", False)
    ss.setdefault("editing_rule_id", None)
    ss.setdefault("show_saved_toast", False)

# --------- CRUD Helpers ---------
def add_rule():
    ss = st.session_state
    rid = ss.next_rule_id
    ss.alert_rules.append({
        "id": rid,
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
        "message": ""
    })
    ss.next_rule_id += 1
    ss.editing_rule_id = rid
    ss.show_alert_rules_dialog = True

def delete_rule(rid: int):
    ss = st.session_state
    ss.alert_rules = [r for r in ss.alert_rules if r["id"] != rid]
    if ss.editing_rule_id == rid:
        ss.editing_rule_id = None

def reset_rules():
    ss = st.session_state
    ss.alert_rules = []
    ss.next_rule_id = 1
    ss.editing_rule_id = None

def save_rule(rid: int):
    ss = st.session_state
    for r in ss.alert_rules:
        if r["id"] == rid:
            r["name"] = ss.get(f"rule_name_{rid}", r["name"])
            r["applied_to"] = ss.get(f"rule_applied_{rid}", [])
            r["uni_common"] = ss.get(f"rule_uni_common_{rid}", r["uni_common"])
            r["common_in"] = ss.get(f"rule_common_in_{rid}", [])
            r["profit_loss"] = ss.get(f"rule_profit_loss_{rid}", r["profit_loss"])
            r["pl_comp"] = ss.get(f"rule_pl_comp_{rid}", r["pl_comp"])
            r["pl_from"] = ss.get(f"rule_pl_from_{rid}", r["pl_from"])
            r["pl_to"] = ss.get(f"rule_pl_to_{rid}", r["pl_to"])
            r["inv_comp"] = ss.get(f"rule_inv_comp_{rid}", r["inv_comp"])
            r["inv_from"] = ss.get(f"rule_inv_from_{rid}", r["inv_from"])
            r["inv_to"] = ss.get(f"rule_inv_to_{rid}", r["inv_to"])
            r["message"] = ss.get(f"rule_message_{rid}", r["message"])
            break
    ss.editing_rule_id = None
    ss.show_alert_rules_dialog = False
    ss.show_saved_toast = True

def cancel_edit():
    st.session_state.editing_rule_id = None
    st.session_state.show_alert_rules_dialog = False

# --------- Dialog Rendering ---------
def _rule_edit_form(rule: dict, portfolios: list):
    rid = rule["id"]
    st.text_input("Alert Name", value=rule.get("name",""), key=f"rule_name_{rid}", placeholder="Name")

    st.markdown("**1. Applied To**")
    all_ports = st.checkbox("All Portfolios", key=f"rule_all_{rid}", value=(not rule["applied_to"]))
    if all_ports:
        st.session_state[f"rule_applied_{rid}"] = []
        applied_display = portfolios
    else:
        st.multiselect("Select Portfolios", portfolios,
                       default=rule["applied_to"], key=f"rule_applied_{rid}")
        applied_display = st.session_state.get(f"rule_applied_{rid}", [])

    st.markdown("**2. Scope**")
    st.radio("Unique / Common", ["Unique","Common"], key=f"rule_uni_common_{rid}",
             index=0 if rule.get("uni_common")=="Unique" else 1, horizontal=True)
    if st.session_state.get(f"rule_uni_common_{rid}") == "Common":
        subset = applied_display if applied_display else portfolios
        st.multiselect("Common Across (subset)", subset,
                       default=rule["common_in"] if rule["common_in"] else subset,
                       key=f"rule_common_in_{rid}")

    st.markdown("**3. Profit / Loss**")
    dir_opts = ["Profit","Loss","Unchanged"]
    current_dir = rule.get("profit_loss","")
    idx_dir = dir_opts.index(current_dir)+1 if current_dir in dir_opts else 0
    direction = st.selectbox("Direction", [""]+dir_opts, index=idx_dir,
                             key=f"rule_profit_loss_{rid}",
                             format_func=lambda v: "Select direction" if v=="" else v)

    if direction and direction != "Unchanged":
        comp_opts = PL_COMP_OPTS
        current_comp = rule.get("pl_comp","")
        idx_comp = comp_opts.index(current_comp)+1 if current_comp in comp_opts else 0
        comp = st.selectbox("Comparator", [""]+comp_opts, index=idx_comp,
                            key=f"rule_pl_comp_{rid}",
                            format_func=lambda v: "Select comparator" if v=="" else v)
        if comp == "Range":
            c1,c2 = st.columns(2)
            with c1:
                st.number_input("From (%)", value=rule.get("pl_from",0.0), step=0.5, key=f"rule_pl_from_{rid}")
            with c2:
                st.number_input("To (%)", value=rule.get("pl_to",0.0), step=0.5, key=f"rule_pl_to_{rid}")
        elif comp in ("Greater Than","Less Than"):
            st.number_input("Value (%)", value=rule.get("pl_from",0.0), step=0.5, key=f"rule_pl_from_{rid}")

    st.markdown("**4. Investment Filter**")
    inv_opts = PL_COMP_OPTS
    current_inv = rule.get("inv_comp","")
    idx_inv = inv_opts.index(current_inv)+1 if current_inv in inv_opts else 0
    inv_comp = st.selectbox("Investment Comparator", [""]+inv_opts, index=idx_inv,
                            key=f"rule_inv_comp_{rid}",
                            format_func=lambda v: "Select comparator" if v=="" else v)
    if inv_comp == "Range":
        c3,c4 = st.columns(2)
        with c3:
            st.number_input("Investment From (₹)", value=float(rule.get("inv_from",0.0)),
                            step=5000.0, key=f"rule_inv_from_{rid}")
        with c4:
            st.number_input("Investment To (₹)", value=float(rule.get("inv_to",0.0)),
                            step=5000.0, key=f"rule_inv_to_{rid}")
    elif inv_comp in ("Greater Than","Less Than"):
        st.number_input("Investment Value (₹)", value=float(rule.get("inv_from",0.0)),
                        step=5000.0, key=f"rule_inv_from_{rid}")

    st.markdown("**5. Message**")
    st.text_area("Message", value=rule.get("message",""), key=f"rule_message_{rid}",
                 height=70, placeholder="Short alert message")

    cols = st.columns([0.5,0.25,0.25])
    with cols[1]:
        if st.button("Save", key=f"save_rule_{rid}"):
            save_rule(rid)
    with cols[2]:
        st.button("Cancel", key=f"cancel_rule_{rid}", on_click=cancel_edit)

def _rules_list_body():
    st.markdown("### Alert Rules")
    cR, cC = st.columns([0.5,0.5])
    with cR:
        st.button("Reset (Delete All)", on_click=reset_rules, type="secondary", use_container_width=True)
    with cC:
        st.button("Close", on_click=cancel_edit, use_container_width=True)

    st.divider()
    if not st.session_state.alert_rules:
        st.info("No rules yet. Use 'Add Rule' in Alerts tab.")
        return
    for r in sorted(st.session_state.alert_rules, key=lambda x: x["id"]):
        cols = st.columns([0.65,0.2,0.15])
        with cols[0]:
            st.write(r["name"] or f"(Unnamed #{r['id']})")
        with cols[1]:
            if st.button("✏️ Edit", key=f"edit_{r['id']}"):
                st.session_state.editing_rule_id = r["id"]
        with cols[2]:
            if st.button("🗑️", key=f"del_{r['id']}"):
                delete_rule(r["id"])
                st.experimental_rerun() if hasattr(st,"experimental_rerun") else st.rerun()

def render_rules_dialog(valid_dfs):
    if not st.session_state.get("show_alert_rules_dialog"):
        return
    portfolios = list(valid_dfs.keys())
    if hasattr(st, "dialog"):
        @st.dialog("Set Alert Rules")
        def _dlg():
            if st.session_state.editing_rule_id:
                rule = next((r for r in st.session_state.alert_rules
                             if r["id"] == st.session_state.editing_rule_id), None)
                if rule:
                    _rule_edit_form(rule, portfolios)
                else:
                    st.warning("Rule not found.")
            else:
                _rules_list_body()
        _dlg()
    else:
        with st.expander("Set Alert Rules", expanded=True):
            if st.session_state.editing_rule_id:
                rule = next((r for r in st.session_state.alert_rules
                             if r["id"] == st.session_state.editing_rule_id), None)
                if rule:
                    _rule_edit_form(rule, portfolios)
            else:
                _rules_list_body()

# --------- Public Tab Renderer ---------
def render_alerts_tab(valid_dfs):
    init_alert_rules_state()
    st.subheader("🚨 Alerts & Opportunities")

    col_add, col_settings = st.columns([0.15,0.15])
    with col_add:
        if st.button("➕ Add Rule", key="add_rule_btn"):
            add_rule()
    with col_settings:
        if st.session_state.alert_rules:
            if st.button("⚙️ Settings", key="alert_settings_btn"):
                st.session_state.show_alert_rules_dialog = True
                st.session_state.editing_rule_id = None

    # Empty state
    if not st.session_state.alert_rules:
        st.info("No alert rules configured. Click Add Rule to create one.")
    else:
        if not valid_dfs:
            st.warning("No portfolios loaded to evaluate alerts.")
        else:
            alerts_df = generate_alerts(valid_dfs, st.session_state.alert_rules)
            if alerts_df.empty:
                st.info("No alerts triggered for current rules.")
            else:
                mode = st.radio("View Mode", ["By Portfolio","By Rule"], horizontal=True, key="alerts_view_mode")
                if mode == "By Portfolio":
                    port = st.selectbox("Select Portfolio", sorted(alerts_df["portfolio"].unique()), key="alerts_port_pick")
                    subset = alerts_df[alerts_df["portfolio"]==port]
                else:
                    rule = st.selectbox("Select Rule", sorted(alerts_df["rule"].unique()), key="alerts_rule_pick")
                    subset = alerts_df[alerts_df["rule"]==rule]
                if subset.empty:
                    st.warning("No matches for selection.")
                else:
                    for _, r in subset.iterrows():
                        st.markdown(
                            f"<div style='background:#f5f5f5;padding:8px;border-radius:6px;margin-bottom:6px'>"
                            f"<b>{r['instrument']}</b> "
                            f"<span style='font-size:0.75rem;color:#555'>(Portfolio: {r['portfolio']} | Rule: {r['rule']})</span><br>"
                            f"<small>{r['message']}</small>"
                            f"</div>",
                            unsafe_allow_html=True
                        )

    # Toast
    if st.session_state.get("show_saved_toast"):
        st.toast("Rule saved")
        st.session_state.show_saved_toast = False

    # Finally render dialog (if requested)
    render_rules_dialog(valid_dfs)
