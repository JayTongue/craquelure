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

data = json.load('articles/tsa/vote_data.json')

df = pd.DataFrame(data)

# Map votes to numeric for aggregation
vote_map = {"Yea": 1, "Nay": -1, "Not Voting": 0}
df["vote_num"] = df["vote"].map(vote_map)

# Aggregate by state — sum gives: 2=both Yea, -2=both Nay, 0=split/abstain
state_df = df.groupby("state").agg(
    vote_sum=("vote_num", "sum"),
    senators=("name", lambda x: "<br>".join(
        f"{row.name} ({row.party}): {row.vote}"
        for _, row in df[df["state"] == x.name].iterrows()
    ))
).reset_index()

# Human-readable label for color
def label(v):
    if v > 0: return "Yea"
    if v < 0: return "Nay"
    return "Split / Not Voting"

state_df["result"] = state_df["vote_sum"].apply(label)

fig = px.choropleth(
    state_df,
    locations="state",
    locationmode="USA-states",
    color="result",
    scope="usa",
    hover_name="state",
    hover_data={"senators": True, "result": False, "vote_sum": False, "state": False},
    color_discrete_map={"Yea": "steelblue", "Nay": "tomato", "Split / Not Voting": "lightgray"},
    title="Senate Vote by State"
)

fig.update_layout(legend_title_text="State Vote")

graph_json = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)