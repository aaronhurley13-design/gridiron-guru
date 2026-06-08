
import streamlit as st
import pandas as pd
import json, io, os

st.set_page_config(page_title="Gridiron Guru", page_icon="🏈", layout="wide")

# ==========================================
# CSS HACK: MAKE MOBILE SIDEBAR VISIBLE 📱
# ==========================================
st.markdown("""
<style>
/* Target the collapsed sidebar button */
[data-testid="collapsedControl"] {
    background-color: #ff4b4b !important; /* Streamlit's primary red */
    border-radius: 50% !important;
    box-shadow: 0px 4px 8px rgba(0, 0, 0, 0.5) !important;
    color: white !important;
    padding: 5px !important;
    z-index: 999999 !important;
}
/* Make the little arrow icon inside it bigger and white */
[data-testid="collapsedControl"] svg {
    fill: white !important;
    width: 28px !important;
    height: 28px !important;
}
/* Add the custom text right next to the arrow! */
[data-testid="collapsedControl"]::after {
    content: "⚙️ Input League Settings";
    position: absolute;
    left: 45px;
    top: 50%;
    transform: translateY(-50%);
    background-color: #ff4b4b;
    color: white;
    padding: 4px 12px;
    border-radius: 15px;
    font-size: 14px;
    font-weight: bold;
    white-space: nowrap;
    box-shadow: 0px 4px 8px rgba(0, 0, 0, 0.4);
    pointer-events: none;
}
</style>
""", unsafe_allow_html=True)

@st.cache_data
def load_initial_player_pool():
    csv_files = [f for f in os.listdir('.') if f.endswith('.csv')]
    if csv_files:
        try:
            df = pd.read_csv(csv_files[0])
            df.columns = df.columns.str.strip().str.lower()
            df.rename(columns={"player": "player_name", "player name": "player_name", "name": "player_name", "pos": "position", "points": "projected_points"}, inplace=True)
            if "position" in df.columns:
                df['position'] = df['position'].astype(str).str.replace(r'\d+', '', regex=True).str.upper()
            if "rank" not in df.columns:
                df['rank'] = range(1, len(df) + 1)
            if "projected_points" not in df.columns:
                df["projected_points"] = 300 - (df["rank"] * 5) # Smart fallback math
            return df
        except Exception: pass
    
    # Fallback dataset with ranks and points for VBD calculations
    csv_data = """rank,player_name,position,bye week,projected_points
1,Christian McCaffrey,RB,9,330
2,CeeDee Lamb,WR,7,315
3,Tyreek Hill,WR,6,310
4,Ja'Marr Chase,WR,12,295
5,Justin Jefferson,WR,6,290
6,Bijan Robinson,RB,12,280
7,Amon-Ra St. Brown,WR,5,285
8,Breece Hall,RB,12,282
9,A.J. Brown,WR,5,265
10,Puka Nacua,WR,6,260
11,Jahmyr Gibbs,RB,5,250
12,Jonathan Taylor,RB,14,245
13,Garrett Wilson,WR,12,255
14,Saquon Barkley,RB,5,240
15,Kyren Williams,RB,6,238"""
    return pd.read_csv(io.StringIO(csv_data))

def build_prompt(picks_list, my_team_id, my_team_name, current_pick, league_config, top_available_df):
    my_picks = [p for p in picks_list if p["team"] == my_team_id]
    roster_text = "\n".join([f"- {p['player']} ({p['position']})" for p in my_picks]) if my_picks else "No players drafted yet."
    available_text = top_available_df.head(15).to_string(index=False) if not top_available_df.empty else "No available players left."
    kicker_rules = ", ".join([f"{row['Points']} pts for {row['Range']}" for row in league_config['kicker']])
    def_rules = ", ".join([f"{row['Points']} pts per {row['Stat']}" for row in league_config['defense']])
    roster_spots = ", ".join([f"{row['Count']} {row['Position']}" for row in league_config['roster']])
    return f"""You are an expert fantasy football draft consultant.
### League Scoring Rules & Roster Constraints
- PPR: {league_config['ppr']} | Pass TD: {league_config['pass_td']} | Rush/Rec TD: {league_config['rush_td']}
- Kickers: {kicker_rules} | Defense: {def_rules} | Roster Setup: {roster_spots}
### Current Draft Situation
- Current Overall Pick: {current_pick} | My Team: {my_team_name}
### My Current Roster
{roster_text}
### Top Available Players
{available_text}
### Instructions
Question: Who should I pick? Consider position scarcity, roster construction, and scoring landmines. Do not recommend K or DST until the final two rounds unless strictly necessary.
Respond ONLY in this JSON Format:
{{"pick": "Player Name", "position": "Position", "reasoning": "2-3 sentences explaining the pick"}}""".strip()

def parse_gemini_response(text):
    t = text.strip()
    if t.startswith('```'):
        first, last = t.find("\n"), t.rfind('```')
        if -1 < first < last: t = t[first:last].strip()
    try: return json.loads(t)
    except: return None

if 'all_players' not in st.session_state: st.session_state.all_players = load_initial_player_pool()
if 'picks' not in st.session_state: st.session_state.picks = []
if 'queue' not in st.session_state: st.session_state.queue = [] 
if 'kicker_scoring' not in st.session_state: st.session_state.kicker_scoring = pd.DataFrame([{"Range": "0-39 yds", "Points": 3}, {"Range": "40-49 yds", "Points": 4}, {"Range": "50+ yds", "Points": 5}, {"Range": "PAT", "Points": 1}])
if 'defense_scoring' not in st.session_state: st.session_state.defense_scoring = pd.DataFrame([{"Stat": "Turnover", "Points": 2}, {"Stat": "Sack", "Points": 1}, {"Stat": "Safety", "Points": 2}])
if 'roster_spots' not in st.session_state: st.session_state.roster_spots = pd.DataFrame([{"Position": "QB", "Count": 1}, {"Position": "RB", "Count": 2}, {"Position": "WR", "Count": 2}, {"Position": "TE", "Count": 1}, {"Position": "FLEX", "Count": 1}, {"Position": "K", "Count": 1}, {"Position": "DST", "Count": 1}, {"Position": "Bench", "Count": 6}])

if 'player_tags' not in st.session_state:
    st.session_state.player_tags = {
        "Christian McCaffrey": "⭐ Target",
        "Breece Hall": "⭐ Target",
        "CeeDee Lamb": "⭐ Target",
        "Puka Nacua": "🟢 Sleeper",
        "Kyren Williams": "🟢 Sleeper",
        "Garrett Wilson": "🟢 Sleeper"
    }

if 'team_names' not in st.session_state or type(st.session_state.team_names) is not pd.DataFrame or "ID" not in st.session_state.team_names.columns:
    st.session_state.team_names = pd.DataFrame([{"ID": i, "Team Name": f"Team {i}"} for i in range(1, 17)])

# ==========================================
# VBD DYNAMIC BASELINE CALCULATION ENGINE 🧮
# ==========================================
def get_vbd_map(df, teams_count):
    baselines = {}
    positions = ["QB", "RB", "WR", "TE"]
    limits = {"QB": teams_count, "RB": teams_count * 2, "WR": teams_count * 2, "TE": teams_count}
    
    for pos in positions:
        pos_players = df[df["position"].str.upper() == pos].sort_values(by="projected_points", ascending=False)
        cutoff = limits[pos]
        if len(pos_players) >= cutoff:
            baselines[pos] = pos_players.iloc[cutoff - 1]["projected_points"]
        elif not pos_players.empty:
            baselines[pos] = pos_players.iloc[-1]["projected_points"]
        else:
            baselines[pos] = 0
            
    vbd_dict = {}
    for _, row in df.iterrows():
        pos = str(row["position"]).upper()
        base = baselines.get(pos, 0)
        vbd_val = row["projected_points"] - base
        vbd_dict[row["player_name"]] = int(vbd_val)
    return vbd_dict

title_col, image_col = st.columns([2, 1])
with title_col: st.title("Gridiron Guru")
with image_col: st.image("logo.png", width=150)

with st.sidebar:
    st.header("⚙️ Settings & Imports")
    uploaded_csv = st.file_uploader("Upload temporary rankings (.csv)", type=["csv"])
    if uploaded_csv is not None:
        try:
            temp_df = pd.read_csv(uploaded_csv)
            temp_df.columns = temp_df.columns.str.strip().str.lower()
            temp_df.rename(columns={"player": "player_name", "player name": "player_name", "name": "player_name", "pos": "position", "points": "projected_points"}, inplace=True)
            if "position" in temp_df.columns: temp_df['position'] = temp_df['position'].astype(str).str.replace(r'\d+', '', regex=True).str.upper()
            if "rank" not in temp_df.columns: temp_df['rank'] = range(1, len(temp_df) + 1)
            if "projected_points" not in temp_df.columns: temp_df["projected_points"] = 300 - (temp_df["rank"] * 5)
            st.session_state.all_players = temp_df
            st.success("Custom player list loaded!")
        except Exception: st.error("Error reading CSV file.")

    uploaded_file = st.file_uploader("Load Saved Config (.json)", type=["json"])
    if uploaded_file is not None:
        try:
            loaded_data = json.load(uploaded_file)
            st.session_state.kicker_scoring = pd.DataFrame(loaded_data["kicker"])
            st.session_state.defense_scoring = pd.DataFrame(loaded_data["defense"])
            st.session_state.roster_spots = pd.DataFrame(loaded_data["roster"])
            st.success("Config loaded!")
        except Exception: st.error("Error reading JSON file.")

    teams = st.number_input("Number of teams", min_value=8, max_value=16, value=12)
    my_team_id = st.number_input("My Team Number", min_value=1, max_value=teams, value=1)
    
    st.markdown("### 🏷️ Custom Team Names")
    edited_teams = st.data_editor(st.session_state.team_names.head(teams), hide_index=True, use_container_width=True)
    team_name_map = dict(zip(edited_teams["ID"], edited_teams["Team Name"]))
    my_team_name = team_name_map.get(my_team_id, f"Team {my_team_id}")

    draft_type = st.radio("Draft Type", options=["Snake", "Linear"], horizontal=True)
    st.markdown("### Basic Scoring")
    ppr = st.slider("PPR value", 0.0, 1.0, 1.0, 0.5)
    pass_td = st.number_input("Pass TD Points", value=4)
    rush_td = st.number_input("Rush/Rec TD Points", value=6)
    
    st.markdown("### 🏈 Roster Size")
    edited_roster = st.data_editor(st.session_state.roster_spots, num_rows="dynamic", use_container_width=True)
    st.markdown("### 🦵 Kicker")
    edited_kicker = st.data_editor(st.session_state.kicker_scoring, num_rows="dynamic", use_container_width=True)
    st.markdown("### 🛡️ Defense")
    edited_defense = st.data_editor(st.session_state.defense_scoring, num_rows="dynamic", use_container_width=True)

    league_config = {"teams": teams, "ppr": ppr, "pass_td": pass_td, "rush_td": rush_td, "draft_type": draft_type, "kicker": edited_kicker.to_dict(orient="records"), "defense": edited_defense.to_dict(orient="records"), "roster": edited_roster.to_dict(orient="records")}
    st.download_button(label="📥 Save Config File", data=json.dumps(league_config, indent=2), file_name="my_league_config.json", mime="application/json")
    if st.button("Reset Draft Board"):
        st.session_state.picks, st.session_state.queue = [], []
        st.session_state.all_players = load_initial_player_pool()
        st.session_state.player_tags = {"Christian McCaffrey": "⭐ Target", "Breece Hall": "⭐ Target", "CeeDee Lamb": "⭐ Target", "Puka Nacua": "🟢 Sleeper", "Kyren Williams": "🟢 Sleeper", "Garrett Wilson": "🟢 Sleeper"}
        st.rerun()

current_pick = len(st.session_state.picks) + 1
drafted_names = [p["player"] for p in st.session_state.picks]
round_num = (current_pick - 1) // teams + 1
pick_in_round = (current_pick - 1) % teams + 1
auto_team_id = (teams - pick_in_round + 1) if (draft_type == "Snake" and round_num % 2 == 0) else pick_in_round

st.session_state.queue = [p for p in st.session_state.queue if p not in drafted_names]
available_df = st.session_state.all_players[~st.session_state.all_players["player_name"].isin(drafted_names)] if "player_name" in st.session_state.all_players.columns else pd.DataFrame()

vbd_map = get_vbd_map(st.session_state.all_players, teams)

def tag_formatter(player_name):
    tag = st.session_state.player_tags.get(player_name, "")
    vbd_score = vbd_map.get(player_name, 0)
    vbd_text = f"VBD: +{vbd_score}" if vbd_score >= 0 else f"VBD: {vbd_score}"
    return f"{player_name} [{vbd_text}] ({tag})" if tag else f"{player_name} [{vbd_text}]"

# ==========================================
# 🚨 FEATURE 2: LIVE OPPONENT NEEDS MATRIX
# ==========================================
st.markdown("---")
col_needs, col_alerts = st.columns(2)

with col_needs:
    st.header("👀 Upcoming Draft Team Needs")
    upcoming_picks_teams = []
    for future_pick_offset in range(4):
        f_pick = current_pick + future_pick_offset
        f_round = (f_pick - 1) // teams + 1
        f_p_in_round = (f_pick - 1) % teams + 1
        f_team_id = (teams - f_p_in_round + 1) if (draft_type == "Snake" and f_round % 2 == 0) else f_p_in_round
        if f_team_id not in upcoming_picks_teams:
            upcoming_picks_teams.append(f_team_id)

    needs_cols = st.columns(len(upcoming_picks_teams))
    for idx, t_id in enumerate(upcoming_picks_teams):
        t_name = team_name_map.get(t_id, f"Team {t_id}")
        t_picks = [p for p in st.session_state.picks if p["team"] == t_id]
        t_positions = [p["position"] for p in t_picks]
        
        with needs_cols[idx]:
            is_me = " (YOU)" if t_id == my_team_id else ""
            st.markdown(f"**📢 {t_name}{is_me}**")
            if t_positions:
                st.caption(f"Filled: {', '.join(t_positions)}")
            else:
                st.caption("No players rostered yet.")

# ==========================================
# ⚠️ TIER DROP "CLIFF EDGE" ALERTS
# ==========================================
with col_alerts:
    st.header("⚠️ Tier Drop Alerts")
    if not available_df.empty:
        alerts = []
        for pos in ["QB", "RB", "WR", "TE"]:
            pos_avail = available_df[available_df["position"] == pos].sort_values("projected_points", ascending=False)
            if len(pos_avail) >= 2:
                top_player = pos_avail.iloc[0]
                next_player = pos_avail.iloc[1]
                diff = top_player["projected_points"] - next_player["projected_points"]
                
                # If there's a 12+ point drop between the best and next best available...
                if diff >= 12:
                    alerts.append(f"**{pos} Cliff:** {top_player['player_name']} is the last in their tier! Next up is {next_player['player_name']} (a drop of {int(diff)} proj. pts).")
        
        if alerts:
            for alert in alerts:
                st.error(alert)
        else:
            st.success("✅ The board is stable. No major positional point cliffs detected right now.")

# ==========================================
# DRAFT QUEUE WITH POSITION FILTER & TAGS 🎯
# ==========================================
st.markdown("---")
st.header("🎯 Draft Queue & Custom Tags")
if not available_df.empty:
    queue_filter = st.radio("Filter Queue by Position:", ["ALL", "QB", "RB", "WR", "TE", "K", "DST"], horizontal=True)
    
    if queue_filter == "ALL":
        filtered_names = available_df["player_name"].tolist()
    else:
        filtered_names = available_df[available_df['position'].str.contains(queue_filter, case=False, na=False)]["player_name"].tolist()
    
    safe_options = list(set(filtered_names + st.session_state.queue))
    safe_options = [str(x) for x in safe_options if pd.notna(x) and str(x).strip() != ""]
    safe_options.sort()
    
    st.session_state.queue = st.multiselect("Search and pin players to your Watchlist:", options=safe_options, default=st.session_state.queue, format_func=tag_formatter)
    
    if st.session_state.queue:
        cols = st.columns(min(len(st.session_state.queue), 4))
        for i, q_player in enumerate(st.session_state.queue):
            with cols[i % 4]: 
                player_tag = st.session_state.player_tags.get(q_player, "No Tag")
                vbd_val = vbd_map.get(q_player, 0)
                st.info(f"📌 {q_player} \n`Tag: {player_tag}` | `VBD: {vbd_val}`")
                
    with st.expander("🏷️ Add / Edit Custom Player Tags"):
        tag_col1, tag_col2 = st.columns(2)
        all_players_list = sorted(list(set(st.session_state.all_players["player_name"].dropna().tolist())))
        with tag_col1:
            target_player = st.selectbox("Select Player to Tag:", options=all_players_list)
        with tag_col2:
            chosen_tag = st.selectbox("Assign Label:", options=["⭐ Target", "🟢 Sleeper", "🔴 Avoid", "Clear Tag"])
            if st.button("Apply Label"):
                if chosen_tag == "Clear Tag":
                    st.session_state.player_tags.pop(target_player, None)
                else:
                    st.session_state.player_tags[target_player] = chosen_tag
                st.success(f"Updated tag for {target_player}!")
                st.rerun()

st.markdown("---")

col1, col2 = st.columns(2)
with col1:
    st.header("📋 Record a Pick")
    if not available_df.empty:
        all_available_names = [str(x) for x in available_df["player_name"].tolist() if pd.notna(x) and str(x).strip() != ""]
        dropdown_options = st.session_state.queue + [p for p in all_available_names if p not in st.session_state.queue]
        
        player = st.selectbox("Player drafted", options=dropdown_options, format_func=tag_formatter)
        team_options = [team_name_map[i] for i in range(1, teams + 1)]
        safe_index = min(max(0, int(auto_team_id) - 1), max(0, len(team_options) - 1))
        
        selected_team_name = st.selectbox(f"Drafting Team (Round {round_num})", options=team_options, index=safe_index, key=f"team_input_{current_pick}")
        team_id = team_options.index(selected_team_name) + 1

        matched = st.session_state.all_players[st.session_state.all_players["player_name"] == player]
        detected_pos = matched["position"].values[0] if not matched.empty else "WR"
        detected_bye = matched["bye week"].values[0] if "bye week" in st.session_state.all_players.columns and not matched.empty else None
        orig_rank = int(matched["rank"].values[0]) if not matched.empty and "rank" in matched.columns else current_pick

        # ==========================================
        # 🚨 FEATURE 1: VALUE & REACH ANALYZER
        # ==========================================
        pick_diff = current_pick - orig_rank
        valuation = "Standard"
        if pick_diff >= 5:
            valuation = "🔥 Value Pick"
        elif pick_diff <= -5:
            valuation = "🎈 Reach"

        btn_col1, btn_col2 = st.columns(2)
        with btn_col1:
            if st.button("Add Pick 🏈"):
                st.session_state.picks.append({
                    "pick": current_pick, 
                    "team_name": selected_team_name, 
                    "team": team_id, 
                    "player": player, 
                    "position": detected_pos, 
                    "bye_week": detected_bye,
                    "analysis": valuation
                })
                st.rerun()
        with btn_col2:
            if st.button("Undo Last Pick ⏪"):
                if st.session_state.picks: st.session_state.picks.pop(); st.rerun()
                else: st.warning("No picks to undo!")
    else: st.write("No remaining players in the database pool.")

with col2:
    st.header("📊 Draft Board")
    
    tab_list, tab_matrix = st.tabs(["📋 List View", "🧱 Grid Matrix View"])
    
    with tab_list:
        if st.session_state.picks:
            display_df = pd.DataFrame(st.session_state.picks)
            if "bye_week" in display_df.columns: display_df = display_df.drop(columns=["bye_week", "team"])
            display_df = display_df.rename(columns={"pick": "Pick", "team_name": "Team", "player": "Player", "position": "Position", "analysis": "Analysis"})
            st.dataframe(display_df, use_container_width=True)
            
            csv_buffer = io.StringIO()
            display_df.to_csv(csv_buffer, index=False)
            st.download_button(label="📥 Export Draft Results (CSV)", data=csv_buffer.getvalue(), file_name="draft_results.csv", mime="text/csv")
        else: st.info("No picks yet")
        
    with tab_matrix:
        total_rounds = int(st.session_state.roster_spots["Count"].sum()) if not st.session_state.roster_spots.empty else 16
        matrix_grid = {team_name_map[i]: ["—"] * total_rounds for i in range(1, teams + 1)}
        
        for p in st.session_state.picks:
            p_round = (p["pick"] - 1) // teams
            p_team_name = team_name_map.get(p["team"])
            
            badge = "🔥 " if p.get("analysis") == "🔥 Value Pick" else ("🎈 " if p.get("analysis") == "🎈 Reach" else "")
            if p_round < total_rounds and p_team_name in matrix_grid:
                matrix_grid[p_team_name][p_round] = f"{badge}{p['player']} ({p['position']})"
                
        matrix_df = pd.DataFrame(matrix_grid, index=[f"Round {i+1}" for i in range(total_rounds)])
        st.dataframe(matrix_df, use_container_width=True)

st.markdown("---")
st.header("📈 My Roster Progress")
my_roster_picks = [p for p in st.session_state.picks if p["team"] == my_team_id]
pos_counts = {}
for p in my_roster_picks: pos_counts[p["position"]] = pos_counts.get(p["position"], 0) + 1

reqs = {row["Position"].upper(): int(row["Count"]) for idx, row in st.session_state.roster_spots.iterrows()}
core_positions = ["QB", "RB", "WR", "TE", "K", "DST"]
flex_eligible = ["RB", "WR", "TE"]
flex_overflow, bench_overflow = 0, 0

for pos in core_positions:
    drafted, req = pos_counts.get(pos, 0), reqs.get(pos, 0)
    overflow = drafted - req
    if overflow > 0:
        if pos in flex_eligible: flex_overflow += overflow
        else: bench_overflow += overflow

req_flex = reqs.get("FLEX", 0)
flex_filled = min(flex_overflow, req_flex)
bench_overflow += (flex_overflow - flex_filled) + sum(count for pos, count in pos_counts.items() if pos not in core_positions)
req_bench = reqs.get("BENCH", 6)

active_cols = sum(1 for pos in core_positions if reqs.get(pos, 0) > 0) + (1 if req_flex > 0 else 0) + (1 if req_bench > 0 else 0)
prog_cols = st.columns(max(active_cols, 1))
col_index = 0

for pos in core_positions:
    req_count = reqs.get(pos, 0)
    if req_count > 0:
        drafted_count = pos_counts.get(pos, 0)
        with prog_cols[col_index]:
            st.write(f"**{pos}** ({min(drafted_count, req_count)}/{req_count})")
            st.progress(min(drafted_count / req_count, 1.0))
        col_index += 1

if req_flex > 0:
    with prog_cols[col_index]:
        st.write(f"**FLEX** ({flex_filled}/{req_flex})"); st.progress(min(flex_filled / req_flex, 1.0))
    col_index += 1

if req_bench > 0:
    with prog_cols[col_index]:
        st.write(f"**BENCH** ({min(bench_overflow, req_bench)}/{req_bench})"); st.progress(min(bench_overflow / req_bench, 1.0) if req_bench > 0 else 1.0)

# ==========================================
# 🗓️ BYE-WEEK HEATMAP
# ==========================================
st.markdown("### 🗓️ Bye-Week Heatmap (My Team)")
my_team_byes = []
for p in my_roster_picks:
    try:
        my_team_byes.append(int(float(p.get("bye_week", 0))))
    except:
        pass

# NFL Bye weeks typically range from Week 5 to 14
bye_counts = {wk: 0 for wk in range(5, 15)}
for bw in my_team_byes:
    if bw in bye_counts:
        bye_counts[bw] += 1

heat_cols = st.columns(len(bye_counts))
for i, (wk, count) in enumerate(bye_counts.items()):
    with heat_cols[i]:
        st.markdown(f"**Wk {wk}**")
        if count == 0:
            st.success(f"{count}")
        elif count == 1:
            st.info(f"{count}")
        elif count == 2:
            st.warning(f"{count}")
        else:
            st.error(f"{count}") # 3 or more players on bye is a huge danger zone!

st.markdown("---")
st.header("🤖 AI Advisor")
if st.button("Generate Gemini Prompt"):
    generated_prompt = build_prompt(st.session_state.picks, my_team_id, my_team_name, current_pick, league_config, available_df)
    st.text_area("Copy this prompt into the Gemini Web App:", value=generated_prompt, height=350)

gemini_input = st.text_area("Paste Gemini's JSON Response below:", height=150)
if st.button("Process AI Recommendation"):
    if gemini_input:
        parsed_data = parse_gemini_response(gemini_input)
        if parsed_data:
            st.success(f"### Recommended Pick: {parsed_data.get('pick')} ({parsed_data.get('position')})")
            st.write(f"**Reasoning:** {parsed_data.get('reasoning')}")
        else: st.error("Could not parse valid JSON. Copy the ENTIRE prompt and response.")
    else: st.warning("Please paste the response into the box first!")
