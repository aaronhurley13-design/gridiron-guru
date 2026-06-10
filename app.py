
import streamlit as st
import pandas as pd
import json, io, os, time

st.set_page_config(page_title="Gridiron Guru", page_icon="🏈", layout="wide")

# ==========================================
# CSS HACK: CLEAN MOBILE FIXES & ZERO SCROLL
# ==========================================
st.markdown("""
<style>
[data-testid="collapsedControl"] {
    background-color: #ff4b4b !important;
    border-radius: 50% !important;
    box-shadow: 0px 4px 8px rgba(0, 0, 0, 0.5) !important;
    color: white !important;
    padding: 5px !important;
    z-index: 999999 !important;
}
[data-testid="collapsedControl"] svg {
    fill: white !important;
    width: 28px !important;
    height: 28px !important;
}
[data-testid="collapsedControl"]::after {
    content: "⚙️ Settings";
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
}
/* Reduce padding to fit more on screen without scrolling */
.block-container {
    padding-top: 1rem !important;
    padding-bottom: 1rem !important;
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
                df["projected_points"] = 300 - (df["rank"] * 5)
            return df
        except Exception: pass
    
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

def get_vbd_map(df, teams_count):
    baselines = {}
    positions = ["QB", "RB", "WR", "TE"]
    limits = {"QB": teams_count, "RB": teams_count * 2, "WR": teams_count * 2, "TE": teams_count}
    for pos in positions:
        pos_players = df[df["position"].str.upper() == pos].sort_values(by="projected_points", ascending=False)
        cutoff = limits[pos]
        if len(pos_players) >= cutoff: baselines[pos] = pos_players.iloc[cutoff - 1]["projected_points"]
        elif not pos_players.empty: baselines[pos] = pos_players.iloc[-1]["projected_points"]
        else: baselines[pos] = 0
            
    vbd_dict = {}
    for _, row in df.iterrows():
        pos = str(row["position"]).upper()
        base = baselines.get(pos, 0)
        vbd_val = row["projected_points"] - base
        vbd_dict[row["player_name"]] = int(vbd_val)
    return vbd_dict

if 'all_players' not in st.session_state: st.session_state.all_players = load_initial_player_pool()
if 'picks' not in st.session_state: st.session_state.picks = []
if 'queue' not in st.session_state: st.session_state.queue = [] 
if 'kicker_scoring' not in st.session_state: st.session_state.kicker_scoring = pd.DataFrame([{"Range": "0-39 yds", "Points": 3}, {"Range": "40-49 yds", "Points": 4}, {"Range": "50+ yds", "Points": 5}, {"Range": "PAT", "Points": 1}])
if 'defense_scoring' not in st.session_state: st.session_state.defense_scoring = pd.DataFrame([{"Stat": "Turnover", "Points": 2}, {"Stat": "Sack", "Points": 1}, {"Stat": "Safety", "Points": 2}])
if 'roster_spots' not in st.session_state: st.session_state.roster_spots = pd.DataFrame([{"Position": "QB", "Count": 1}, {"Position": "RB", "Count": 2}, {"Position": "WR", "Count": 2}, {"Position": "TE", "Count": 1}, {"Position": "FLEX", "Count": 1}, {"Position": "K", "Count": 1}, {"Position": "DST", "Count": 1}, {"Position": "Bench", "Count": 6}])
if 'player_tags' not in st.session_state: st.session_state.player_tags = {"Christian McCaffrey": "⭐ Target", "Breece Hall": "⭐ Target", "CeeDee Lamb": "⭐ Target", "Puka Nacua": "🟢 Sleeper", "Kyren Williams": "🟢 Sleeper", "Garrett Wilson": "🟢 Sleeper"}
if 'team_names' not in st.session_state or type(st.session_state.team_names) is not pd.DataFrame or "ID" not in st.session_state.team_names.columns:
    st.session_state.team_names = pd.DataFrame([{"ID": i, "Team Name": f"Team {i}"} for i in range(1, 17)])
if 'clock_starts' not in st.session_state: st.session_state.clock_starts = {}

if 'last_pick_count' not in st.session_state: st.session_state.last_pick_count = 0
current_pick_count = len(st.session_state.picks)

if current_pick_count > st.session_state.last_pick_count:
    st.markdown("""<audio autoplay style="display:none;"><source src="https://assets.mixkit.co/active_storage/sfx/2013/2013-preview.mp3" type="audio/mpeg"></audio>""", unsafe_allow_html=True)
    st.session_state.last_pick_count = current_pick_count
elif current_pick_count < st.session_state.last_pick_count:
    st.session_state.last_pick_count = current_pick_count

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
    if st.button("Reset Draft Board"):
        st.session_state.picks, st.session_state.queue = [], []
        st.session_state.all_players = load_initial_player_pool()
        st.session_state.player_tags = {"Christian McCaffrey": "⭐ Target", "Breece Hall": "⭐ Target", "CeeDee Lamb": "⭐ Target", "Puka Nacua": "🟢 Sleeper", "Kyren Williams": "🟢 Sleeper", "Garrett Wilson": "🟢 Sleeper"}
        st.session_state.clock_starts = {}
        st.rerun()

current_pick = len(st.session_state.picks) + 1
drafted_names = [p["player"] for p in st.session_state.picks]
round_num = (current_pick - 1) // teams + 1
pick_in_round = (current_pick - 1) % teams + 1
auto_team_id = (teams - pick_in_round + 1) if (draft_type == "Snake" and round_num % 2 == 0) else pick_in_round

st.session_state.queue = [p for p in st.session_state.queue if p not in drafted_names]
available_df = st.session_state.all_players[~st.session_state.all_players["player_name"].isin(drafted_names)] if "player_name" in st.session_state.all_players.columns else pd.DataFrame()

vbd_map = get_vbd_map(st.session_state.all_players, teams)

def get_depletion(pos):
    req_per_team = sum([int(r["Count"]) for _, r in st.session_state.roster_spots.iterrows() if r["Position"].upper() == pos])
    if req_per_team == 0: req_per_team = 1
    total_expected = req_per_team * teams
    drafted_count = sum(1 for dp in st.session_state.picks if dp["position"] == pos)
    return min((drafted_count / total_expected) * 100, 100) if total_expected > 0 else 0

# ==========================================
# 🏷️ APP LOGO
# ==========================================
try:
    st.image("IMG_0106.png", width=200)
except Exception:
    pass

# ==========================================
# 📺 LIVE BROADCAST TICKER
# ==========================================
if st.session_state.picks:
    recent_picks = st.session_state.picks[-10:]
    ticker_str = "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;🏈&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;".join(
        [f"Pick {p['pick']}: {p['player']} ({p['position']}) — {p['team_name']}" for p in recent_picks]
    )
    ticker_html = f"""
    <div style="background-color: #1e1e1e; border-top: 2px solid #ff4b4b; border-bottom: 2px solid #ff4b4b; padding: 4px 0; margin-bottom: 10px;">
        <marquee scrollamount="6" style="color: white; font-weight: bold; font-size: 16px; font-family: sans-serif;">{ticker_str}</marquee>
    </div>"""
    st.markdown(ticker_html, unsafe_allow_html=True)

# ==========================================
# 🖥️ ZERO-SCROLL 3-COLUMN LAYOUT
# ==========================================
col_left, col_center, col_right = st.columns([35, 35, 30])

with col_left:
    st.subheader("📋 Log Pick")
    
    # Live Clock Setup
    clock_key = f"pick_{current_pick}"
    start_time = st.session_state.clock_starts.get(clock_key)
    if start_time is None:
        if st.button(f"▶️ Start Pick {current_pick} Clock", use_container_width=True):
            st.session_state.clock_starts[clock_key] = time.time()
            st.rerun()
    else:
        timer_html = f"""
        <div id="timer-box" style="font-family:sans-serif; text-align:center; padding:8px; background-color:#1e1e1e; color:white; border-radius:8px; border: 2px solid #2e2e2e; margin-bottom:10px;">
          <div id="clock" style="font-size:28px; font-weight:bold; color:#00ff00; line-height:1;">--</div>
        </div>
        <script>
          var startTime = {start_time} * 1000;
          var duration = 90 * 1000;
          var endTime = startTime + duration;
          var clockEl = document.getElementById('clock');
          var timerBox = document.getElementById('timer-box');
          var tickAudio = new Audio('https://assets.mixkit.co/active_storage/sfx/2568/2568-preview.mp3');
          var buzzAudio = new Audio('https://assets.mixkit.co/active_storage/sfx/2955/2955-preview.mp3');
          var buzzerPlayed = false; var tickPlayed = false;
          function update() {{
            var now = new Date().getTime();
            var timeLeft = Math.max(0, Math.ceil((endTime - now) / 1000));
            clockEl.innerText = timeLeft;
            if (timeLeft <= 10 && timeLeft > 0) {{
              clockEl.style.color = '#ff4b4b'; timerBox.style.borderColor = '#ff4b4b';
              if(!tickPlayed) {{ tickAudio.play(); tickPlayed = true; setTimeout(()=>{{tickPlayed=false;}}, 900); }}
            }} else if (timeLeft <= 0) {{
              clockEl.innerText = "TIME OUT 🚨"; clockEl.style.color = '#ff4b4b';
              if(!buzzerPlayed) {{ buzzAudio.play(); buzzerPlayed = true; }}
            }}
          }}
          update(); setInterval(update, 1000);
        </script>"""
        st.components.v1.html(timer_html, height=55, scrolling=False)

    # Drafting Team Selector
    team_options = [team_name_map[i] for i in range(1, teams + 1)]
    safe_index = min(max(0, int(auto_team_id) - 1), max(0, len(team_options) - 1))
    selected_team_name = st.selectbox(f"On the clock (Rd {round_num} Pk {current_pick}):", options=team_options, index=safe_index)
    team_id = team_options.index(selected_team_name) + 1

    # Predictive Fast-Type Search Bar
    search_query = st.text_input("🔍 Fast-Search Player Name:", placeholder="Type 2-3 letters (e.g. McC)...").strip()
    
    if search_query and not available_df.empty:
        search_results = available_df[available_df["player_name"].str.contains(search_query, case=False, na=False)].head(4)
        if not search_results.empty:
            st.markdown("**Search Matches:**")
            for _, s_row in search_results.iterrows():
                p_name = s_row["player_name"]
                p_pos = s_row["position"]
                vbd_val = vbd_map.get(p_name, 0)
                
                if st.button(f"🏈 Draft {p_name} ({p_pos}) [VBD: +{vbd_val}]", key=f"search_dr_{p_name}", use_container_width=True):
                    orig_rank = int(s_row["rank"]) if "rank" in s_row else current_pick
                    valuation = "🔥 Value Pick" if (current_pick - orig_rank) >= 5 else ("🎈 Reach" if (current_pick - orig_rank) <= -5 else "Standard")
                    st.session_state.picks.append({
                        "pick": current_pick, "team_name": selected_team_name, "team": team_id, 
                        "player": p_name, "position": p_pos, "bye_week": s_row.get("bye week"), "analysis": valuation
                    })
                    st.rerun()
        else:
            st.caption("No matching available players found.")

    st.markdown("---")
    st.markdown("📍 **Pinned Watchlist**")
    all_available_names = sorted([str(x) for x in available_df["player_name"].tolist() if pd.notna(x)]) if not available_df.empty else []
    st.session_state.queue = st.multiselect("Pin players:", options=all_available_names, default=st.session_state.queue)
    
    if st.session_state.queue:
        for q_player in st.session_state.queue:
            q_match = available_df[available_df["player_name"] == q_player]
            if not q_match.empty:
                q_row = q_match.iloc[0]
                if st.button(f"📌 Draft {q_player} ({q_row['position']})", key=f"q_dr_{q_player}", use_container_width=True):
                    orig_rank = int(q_row["rank"]) if "rank" in q_row else current_pick
                    valuation = "🔥 Value Pick" if (current_pick - orig_rank) >= 5 else ("🎈 Reach" if (current_pick - orig_rank) <= -5 else "Standard")
                    st.session_state.picks.append({
                        "pick": current_pick, "team_name": selected_team_name, "team": team_id, 
                        "player": q_player, "position": q_row["position"], "bye_week": q_row.get("bye week"), "analysis": valuation
                    })
                    st.rerun()

    if st.session_state.picks:
        if st.button("Undo Last Pick ⏪", use_container_width=True):
            st.session_state.picks.pop()
            st.session_state.clock_starts.pop(f"pick_{current_pick-1}", None)
            st.rerun()

with col_center:
    st.subheader("🧱 Draft Matrix")
    tab_matrix, tab_list = st.tabs(["Grid Board", "List View"])
    with tab_matrix:
        total_rounds = int(st.session_state.roster_spots["Count"].sum()) if not st.session_state.roster_spots.empty else 16
        matrix_grid = {team_name_map[i]: ["—"] * total_rounds for i in range(1, teams + 1)}
        for p in st.session_state.picks:
            p_round = (p["pick"] - 1) // teams
            p_team_name = team_name_map.get(p["team"])
            badge = "🔥 " if p.get("analysis") == "🔥 Value Pick" else ("🎈 " if p.get("analysis") == "🎈 Reach" else "")
            if p_round < total_rounds and p_team_name in matrix_grid:
                matrix_grid[p_team_name][p_round] = f"{badge}{p['player']} ({p['position']})"
        st.dataframe(pd.DataFrame(matrix_grid, index=[f"R{i+1}" for i in range(total_rounds)]), use_container_width=True, height=350)
    
    with tab_list:
        if st.session_state.picks:
            display_df = pd.DataFrame(st.session_state.picks)[["pick", "team_name", "player", "position", "analysis"]]
            st.dataframe(display_df, use_container_width=True, height=300, hide_index=True)

with col_right:
    my_roster_picks = [p for p in st.session_state.picks if p["team"] == my_team_id]
    pos_counts = {}
    for p in my_roster_picks: pos_counts[p["position"]] = pos_counts.get(p["position"], 0) + 1
    reqs = {row["Position"].upper(): int(row["Count"]) for idx, row in st.session_state.roster_spots.iterrows()}
    
    my_needs = []
    for pos in ["QB", "RB", "WR", "TE", "K", "DST"]:
        if pos_counts.get(pos, 0) < reqs.get(pos, 0):
            my_needs.append(pos)

    # Algorithmic Top 3 Recommendations
    st.subheader("🧠 Guru's Top 3 Recommendations")
    if not available_df.empty:
        target_df = available_df.copy()
        if my_needs:
            target_df = target_df[target_df['position'].isin(my_needs)]
        if not target_df.empty:
            target_df['guru_score'] = target_df.apply(lambda r: vbd_map.get(r['player_name'], 0) + (get_depletion(r['position']) * 0.5), axis=1)
            top_3 = target_df.sort_values('guru_score', ascending=False).head(3)
            
            for _, p_row in top_3.iterrows():
                p_n = p_row['player_name']
                p_p = p_row['position']
                v_s = vbd_map.get(p_n, 0)
                if st.button(f"🥇 Draft {p_n} ({p_p}) [VBD: +{v_s}]", key=f"guru_dr_{p_n}", use_container_width=True):
                    orig_rank = int(p_row["rank"]) if "rank" in p_row else current_pick
                    valuation = "🔥 Value Pick" if (current_pick - orig_rank) >= 5 else ("🎈 Reach" if (current_pick - orig_rank) <= -5 else "Standard")
                    st.session_state.picks.append({
                        "pick": current_pick, "team_name": selected_team_name, "team": team_id, 
                        "player": p_n, "position": p_p, "bye_week": p_row.get("bye week"), "analysis": valuation
                    })
                    st.rerun()
        else:
            st.caption("No remaining players match your starting needs.")

    st.markdown("---")
    st.subheader("📈 My Squad Roster Tracker")
    for pos in ["QB", "RB", "WR", "TE"]:
        req_count = reqs.get(pos, 0)
        if req_count > 0:
            drafted_count = pos_counts.get(pos, 0)
            st.caption(f"**{pos}** ({min(drafted_count, req_count)}/{req_count})")
            st.progress(min(drafted_count / req_count, 1.0))

    # Live Standings Projection
    st.markdown("---")
    st.subheader("📊 Standing Projections")
    if "player_name" in st.session_state.all_players.columns and "projected_points" in st.session_state.all_players.columns:
        points_map = dict(zip(st.session_state.all_players["player_name"], st.session_state.all_players["projected_points"]))
        standings_data = []
        for i in range(1, teams + 1):
            t_name = team_name_map.get(i, f"Team {i}")
            t_picks = [p for p in st.session_state.picks if p["team"] == i]
            t_pts = sum(points_map.get(p["player"], 0) for p in t_picks)
            standings_data.append({"Team": t_name, "Projected Points": t_pts})
        standings_df = pd.DataFrame(standings_data).sort_values(by="Projected Points", ascending=False)
        st.dataframe(standings_df, hide_index=True, use_container_width=True, height=140)

# Deep Analytics Panel Hidden below
st.markdown("---")
with st.expander("🤖 External AI Advisor & Deep Analytics Panel"):
    if st.button("Generate Gemini Prompt"):
        generated_prompt = build_prompt(st.session_state.picks, my_team_id, my_team_name, current_pick, league_config, available_df)
        st.text_area("Prompt:", value=generated_prompt, height=200)
    gemini_input = st.text_area("Paste Response JSON:")
    if st.button("Process Recommendation"):
        parsed_data = parse_gemini_response(gemini_input)
        if parsed_data: st.success(f"AI Choice: {parsed_data.get('pick')}")
