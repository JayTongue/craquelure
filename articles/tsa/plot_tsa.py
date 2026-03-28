# import requests
# from bs4 import BeautifulSoup
# import re
# from pprint import pprint
# import pandas as pd
# import json

# senate_url = 'https://www.senate.gov/legislative/LIS/roll_call_votes/vote1192/vote_119_2_00061.htm#position'

# senate_page = requests.get(senate_url).text
# # print(senate_page.text)

# pat = r'<br>.*? \(\w-\w\w\), <b>.*?</b>'

# votes = re.findall(pat, senate_page)

# # pprint(votes) ; print(len(votes))

# names, parties, states, responses = [], [], [], []
# for vote in votes:
#     name = re.findall(r'<br>(.*?) \(', vote)[0]
#     party, state = re.findall(r'\((.*?)\)', vote)[0].split('-')
#     response = re.findall(r'<b>(.*?)</b>', vote)[0]
#     # print(vote, name, party, state, response)
#     names.append(name)
#     parties.append(party)
#     states.append(state)
#     responses.append(response)

# with open('articles/tsa/vote_data.json', 'w') as outfile:
#     json.dump({'name': names, 'party': parties, 'state':states, 'vote':responses}, outfile, indent=4)

import pandas as pd
import plotly.express as px
import plotly
import json

with open('articles/tsa/vote_data.json', 'r') as infile:
    data = json.load(infile)

df = pd.DataFrame(data)

# Map votes to numeric for aggregation
vote_map = {"Yea": 1, "Nay": -1, "Not Voting": 0}
df["vote_num"] = df["vote"].map(vote_map)

# Human-readable label for color
def label(v):
    if v > 0: return "Yea"
    if v < 0: return "Nay"
    return "Split / Not Voting"

state_df = df.groupby("state").agg(
    vote_sum=("vote_num", "sum"),
    senators=("name", lambda x: "<br>".join(
        f"{name} ({df.loc[i, 'party']}): {df.loc[i, 'vote']}"
        for i, name in x.items()
    ))
).reset_index()

state_df["result"] = state_df["vote_sum"].apply(label)

# fig = px.choropleth(
#     state_df,
#     locations="state",
#     locationmode="USA-states",
#     color="result",
#     scope="usa",
#     hover_name="state",
#     hover_data={"senators": True, "result": False, "vote_sum": False, "state": False},
#     color_discrete_map={"Yea": "lightgray", "Nay": "tomato", "Split / Not Voting": "lightgray"},
#     # title="Senate Vote by State"
# )

fig = px.choropleth(
    state_df,
    locations="state",
    locationmode="USA-states",
    color="result",
    scope="usa",
    hover_name="state",
    custom_data=["senators"],
    color_discrete_map={"Yea": "lightgray", "Nay": "tomato", "Split / Not Voting": "lightgray"},
)

fig.update_traces(hovertemplate="<b>%{hovertext}</b><br>%{customdata[0]}<extra></extra>")

fig.update_layout(
    dragmode=False,
    geo=dict(
        fitbounds="locations",
        visible=False
    )
)
# fig.update_layout(legend_title_text="Senators by Suck")
fig.update_layout(
    paper_bgcolor='#333',
    plot_bgcolor='#333',
    geo_bgcolor='#333',
    font_color='white'
)
fig.update_layout(showlegend=False)
graph_json = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)

with open('static/images/map_data.js', 'w') as f:
    f.write(f'const figData = {graph_json};')