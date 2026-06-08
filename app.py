
import streamlit as st
import pandas as pd
import json, io, os

st.set_page_config(page_title="Gridiron Guru", page_icon="🏈", layout="wide")

@st.cache_data
def load_initial_player_pool():
    csv_files = [f for f in os.listdir('.') if f.endswith('.csv')]
    if csv_files:
        try:
            df = pd.read_csv(csv_files[0])
            df.columns = df.columns.str.strip().str.lower()
            df.rename(columns={"player": "player_name", "player name": "player_name", "name": "player_name", "pos": "position"}, inplace=True)
            if "position" in df.columns:
                df['position'] = df['position'].astype(str).str.replace(r'\d+', '', regex=True)
            return df
        except Exception: pass
    return pd.read_csv(io.StringIO("player_name,position,bye week\nChristian McCaffrey,RB,9\nCeeDee Lamb,WR,7\nTyreek Hill,WR,6\nJa'Marr Chase,WR,12\nJustin Jefferson,WR,6\nBijan Robinson,RB,12\nAmon-Ra St. Brown,WR,5\nBreece Hall,RB,12\nA.J. Brown,WR,5\nPuka Nacua,WR,6\nJahmyr Gibbs,RB,5\nJonathan Taylor,RB,14\nGarrett Wilson,WR,12\nSaquon Barkley,RB,5\nKyren Williams,RB,6"))

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

if 'team_names' not in st.session_state or type(st.session_state.team_names) is not pd.DataFrame or "ID" not in st.session_state.team_names.columns:
    st.session_state.team_names = pd.DataFrame([{"ID": i, "Team Name": f"Team {i}"} for i in range(1, 17)])

title_col, image_col = st.columns([2, 1])
with title_col: st.title("Gridiron Guru")
with image_col: st.image("https://neon-factory.com/cdn/shop/products/helmet-512-American_-football_-football-club_-helmet_-safety_-soccer_-sport_eecf343f-8f31-4c95-adde-61901ee87fea_1024x1024@2x.png?v=1575240399", width=150)

with st.sidebar:
    st.header("⚙️ Settings & Imports")
    uploaded_csv = st.file_uploader("Upload temporary rankings (.csv)", type=["csv"])
    if uploaded_csv is not None:
        try:
            temp_df = pd.read_csv(uploaded_csv)
            temp_df.columns = temp_df.columns.str.strip().str.lower()
            temp_df.rename(columns={"player": "player_name", "player name": "player_name", "name": "player_name", "pos": "position"}, inplace=True)
            if "position" in temp_df.columns: temp_df['position'] = temp_df['position'].astype(str).str.replace(r'\d+', '', regex=True)
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
        st.rerun()

current_pick = len(st.session_state.picks) + 1
drafted_names = [p["player"] for p in st.session_state.picks]
round_num = (current_pick - 1) // teams + 1
pick_in_round = (current_pick - 1) % teams + 1
auto_team_id = (teams - pick_in_round + 1) if (draft_type == "Snake" and round_num % 2 == 0) else pick_in_round

st.session_state.queue = [p for p in st.session_state.queue if p not in drafted_names]
available_df = st.session_state.all_players[~st.session_state.all_players["player_name"].isin(drafted_names)] if "player_name" in st.session_state.all_players.columns else pd.DataFrame()

# ==========================================
# DRAFT QUEUE WITH POSITION FILTER 🎯
# ==========================================
st.markdown("---")
st.header("🎯 Draft Queue")
if not available_df.empty:
    queue_filter = st.radio("Filter Queue by Position:", ["ALL", "QB", "RB", "WR", "TE", "K", "DST"], horizontal=True)

    if queue_filter == "ALL":
        filtered_names = available_df["player_name"].tolist()
    else:
        filtered_names = available_df[available_df['position'].str.contains(queue_filter, case=False, na=False)]["player_name"].tolist()

    # 🚨 THE FIX: Scrub out any NaN or blank values before sorting
    safe_options = list(set(filtered_names + st.session_state.queue))
    safe_options = [str(x) for x in safe_options if pd.notna(x) and str(x).strip() != ""]
    safe_options.sort()

    st.session_state.queue = st.multiselect("Search and pin players to your Watchlist:", options=safe_options, default=st.session_state.queue)

    if st.session_state.queue:
        cols = st.columns(min(len(st.session_state.queue), 4))
        for i, q_player in enumerate(st.session_state.queue):
            with cols[i % 4]: st.info(f"📌 {q_player}")
st.markdown("---")

col1, col2 = st.columns(2)
with col1:
    st.header("📋 Record a Pick")
    if not available_df.empty:
        # Scrub the main dropdown list as well just to be totally safe!
        all_available_names = [str(x) for x in available_df["player_name"].tolist() if pd.notna(x) and str(x).strip() != ""]
        dropdown_options = st.session_state.queue + [p for p in all_available_names if p not in st.session_state.queue]

        player = st.selectbox("Player drafted", options=dropdown_options)
        team_options = [team_name_map[i] for i in range(1, teams + 1)]
        safe_index = min(max(0, int(auto_team_id) - 1), max(0, len(team_options) - 1))

        selected_team_name = st.selectbox(f"Drafting Team (Round {round_num})", options=team_options, index=safe_index, key=f"team_input_{current_pick}")
        team_id = team_options.index(selected_team_name) + 1

        matched = st.session_state.all_players[st.session_state.all_players["player_name"] == player]
        detected_pos = matched["position"].values[0] if not matched.empty else "WR"
        detected_bye = matched["bye week"].values[0] if "bye week" in st.session_state.all_players.columns and not matched.empty else None

        if team_id == my_team_id and pd.notna(detected_bye):
            my_current_roster = [p for p in st.session_state.picks if p["team"] == my_team_id]
            if [p["player"] for p in my_current_roster if p["position"] == detected_pos and p.get("bye_week") == detected_bye]:
                st.error(f"🚨 **Bye-Week Collision:** You already drafted a **{detected_pos}** that has a Week {int(detected_bye)} bye!")

        btn_col1, btn_col2 = st.columns(2)
        with btn_col1:
            if st.button("Add Pick 🏈"):
                st.session_state.picks.append({"pick": current_pick, "team_name": selected_team_name, "team": team_id, "player": player, "position": detected_pos, "bye_week": detected_bye})
                st.rerun()
        with btn_col2:
            if st.button("Undo Last Pick ⏪"):
                if st.session_state.picks: st.session_state.picks.pop(); st.rerun()
                else: st.warning("No picks to undo!")
    else: st.write("No remaining players in the database pool.")

with col2:
    st.header("📊 Draft Board")
    if st.session_state.picks:
        display_df = pd.DataFrame(st.session_state.picks)
        if "bye_week" in display_df.columns: display_df = display_df.drop(columns=["bye_week", "team"])
        display_df = display_df.rename(columns={"pick": "Pick", "team_name": "Team", "player": "Player", "position": "Position"})
        st.dataframe(display_df, use_container_width=True)
    else: st.info("No picks yet")

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


%%bash
mkdir -p .streamlit
cat <<EOF > .streamlit/config.toml
[theme]
primaryColor = "#00FFFF" 
backgroundColor = "#0E1117"
secondaryBackgroundColor = "#1E2530"
textColor = "#FFFFFF"
font = "sans serif"
EOF
