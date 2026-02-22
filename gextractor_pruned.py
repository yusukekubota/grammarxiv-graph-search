"""
Pruned from the attached gextractor.py:
- Keeps only the functions invoked by the "本体" section (graph search tabs),
  plus the functions/variables they depend on.
- Removes authentication, PDF/bib extraction, DB update utilities, and other UI pages.

Note: This script still expects the same local data files as the original:
  ./result/entries.tsv
  ./result/rels.tsv
  ./result/rels_w_type.tsv
  ./result/entry_names.txt (auto-generated via ./read_entries.rb if missing)
"""

import os
import re
import subprocess
from functools import reduce
from urllib.parse import quote

import pandas as pd
import streamlit as st
import graphviz
from PIL import Image


##############################################################
# Constants / global lists (used by the kept UI)
##############################################################

neovis_url = "https://grammarxiv.net/entry?cql="

bib_types = """article
proceedings-article
bathesis
book
incollection
inproceedings
journal-article
mathesis
misc
ms
phdthesis
unpublished""".split("\n")

hyp_types = ["hypothesis"]
framework_types = ["framework"]
data_types = ["acceptability", "generalization", "report", "other"]
topic_types = ["keyword", "language", "vocabulary", "research_question"]

entry_types = bib_types + hyp_types + data_types + topic_types + framework_types
entry_super_types = ["publication", "hypothesis", "framework", "data", "topic"]

rel_list = """truecite
can_explain
uncertain
equivalent
incompatible
falsecite
subtopic_of
less_acceptable_than
related_topic
other
author_of
refer_to
entail""".split("\n")

rel_list_reverse = """is_trued_by
can_be_explained_by
is_falsed_by
is_entailed_by""".split("\n")

from_candidate_types = {
    "truecite": ["publication"],
    "falsecite": ["publication"],
    "uncertain": ["publication"],
    "can_explain": ["hypothesis", "framework"],
    "incompatible": ["publication", "hypothesis", "framework", "data"],
    "subtopic_of": ["topic"],
    "related_topic": ["publication", "hypothesis", "framework", "data", "topic"],
    "other": ["publication", "hypothesis", "framework", "data", "topic", "experiment"],
    "author_of": ["author"],
    "refer_to": ["publication"],
    "entail": ["hypothesis", "framework", "data"],
    "equivalent": ["publication", "hypothesis", "framework", "data", "topic"],
    "less_acceptable_than": ["data"],
}

to_candidate_types = {
    "truecite": ["publication", "hypothesis", "framework", "data"],
    "falsecite": ["publication", "hypothesis", "framework", "data"],
    "uncertain": ["publication", "hypothesis", "framework", "data"],
    "can_explain": ["data"],
    "incompatible": ["publication", "hypothesis", "framework", "data"],
    "subtopic_of": ["topic"],
    "related_topic": ["topic"],
    "other": ["publication", "hypothesis", "framework", "data", "topic", "experiment"],
    "author_of": ["publication"],
    "refer_to": ["publication"],
    "entail": ["hypothesis", "framework", "data"],
    "equivalent": ["publication", "hypothesis", "framework", "data", "topic"],
    "less_acceptable_than": ["data"],
}


##############################################################
# Data-loading helpers (kept because graph search UI depends on them)
##############################################################

def load_entry_names():
    """
    Ensures ./result/entry_names.txt exists and returns its lines.
    If missing, runs: ruby ./read_entries.rb
    """
    file_path = "./result/entry_names.txt"
    directory_path = "./result"

    if not os.path.exists(directory_path):
        os.makedirs(directory_path)

    if not os.path.exists(file_path):
        try:
            result = subprocess.run(
                "ruby ./read_entries.rb",
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            if result.returncode != 0:
                raise RuntimeError(f"Ruby script failed: {result.stderr}")
        except Exception as e:
            raise RuntimeError(f"Failed to create entry_names.txt: {e}")

    try:
        return open(file_path, "r").read().split("\n")
    except Exception as e:
        raise RuntimeError(f"Failed to read entry_names.txt: {e}")


entry_name_list = None
with st.spinner("[load_entry_names] Initializing..."):
    try:
        entry_name_list = load_entry_names()
    except RuntimeError as e:
        st.error(f"Error: {e}")
        entry_name_list = []


@st.cache_data
def load_relations():
    return pd.read_csv("./result/rels.tsv", sep="\t")


@st.cache_data
def load_entries():
    return pd.read_csv("./result/entries.tsv", sep="\t")


@st.cache_data
def load_rels_w_type():
    return pd.read_csv("./result/rels_w_type.tsv", sep="\t").dropna()


if "rels_df" not in st.session_state:
    st.session_state.rels_df = load_relations()

if "entries_df" not in st.session_state:
    st.session_state.entries_df = load_entries()

author_entry_name_list = (
    st.session_state.entries_df[st.session_state.entries_df["type"] == "author"].name.tolist()
)
topic_entry_name_list = (
    st.session_state.entries_df[st.session_state.entries_df["type"] == "topic"].name.tolist()
)
hypothesis_entry_name_list = (
    st.session_state.entries_df[st.session_state.entries_df["type"] == "hypothesis"].name.tolist()
)
framework_entry_name_list = (
    st.session_state.entries_df[st.session_state.entries_df["type"] == "framework"].name.tolist()
)


##############################################################
# Formatting helpers (kept because easy_query_* uses them)
##############################################################

def orig_rel(label: str) -> str:
    mapping = {
        "is_trued_by": "truecite",
        "can_be_explained_by": "can_explain",
        "is_falsed_by": "falsecite",
        "is_entailed_by": "entail",
    }
    return mapping[label]


def reverse_rel(label: str) -> str:
    mapping = {
        "truecite": "is_trued_by",
        "can_explain": "can_be_explained_by",
        "falsecite": "is_falsed_by",
        "entail": "is_entailed_by",
    }
    return mapping.get(label, "")


def format_node(label: str) -> str:
    if label in (entry_super_types + entry_types):
        return f"(:{label})"
    elif label == "ANY":
        return "()"
    else:
        return f'({{name: "{label}"}})'


def format_node2(label: str, var: str) -> str:
    return f"({var}: {label})"


def format_edge(label: str) -> str:
    if label == "R":
        return "--"
    elif label in rel_list_reverse:
        return f"<-[:{orig_rel(label)}]-"
    else:
        return f"-[:{label}]->"


def format_query_chunk(label: str) -> str:
    if label in (rel_list + rel_list_reverse + ["R"]):
        return format_edge(label)
    else:
        return format_node(label)


def format_query_chain_alt(labels_list):
    s = list(map(lambda l: format_query_chunk(l), labels_list))
    return " ".join(s).replace(") (", ") -- (")


def format_easy_query(key_names, target_node_type, length):
    paths = list(
        map(
            lambda x: "p"
            + str(x[0])
            + "= "
            + format_node2(target_node_type, "a")
            + " -[*.."
            + str(length)
            + "] - "
            + format_node(x[1])
            + f'WHERE ALL(r IN relationships(p{str(x[0])}) WHERE (r.variant <> "REFER_TO") AND (r.variant <> "BADGED_VERIFIED"))',
            enumerate(key_names),
        )
    )
    paths_string = ", ".join(paths)
    r_string = ", ".join(
        list(map(lambda x: "relationships(p" + str(x[0]) + ")", enumerate(key_names)))
    )
    return f"match {paths_string} return *, {r_string}"


def format_easy_query_author_disagree(easy_author_id):
    return f"""match p = {format_node(easy_author_id)}-[:author_of]->{format_node("publication")}-[:true]->{format_node("hypothesis")}<-[:false]-{format_node("publication")}  return *, relationships(p)
union
match p = {format_node(easy_author_id)}-[:author_of]->{format_node("publication")}-[:false]->{format_node("hypothesis")}<-[:true]-{format_node("publication")}  return *, relationships(p)"""


def format_easy_query_author_agree(easy_author_id):
    return f"""match p = {format_node(easy_author_id)}-[:author_of]->{format_node("publication")}-[:true]->{format_node("hypothesis")}<-[:true]-{format_node("publication")}  return *, relationships(p)"""


def format_easy_query_author_same_topic(easy_author_id):
    return f"""match p = {format_node(easy_author_id)}-[:author_of]->{format_node("publication")}-[:related_topic]->{format_node("keyword")}<-[:related_topic]-{format_node("publication")}  return *, relationships(p)"""


def add_header(s: str):
    return st.markdown(f"---\n### {s}")


def neo4j_url(string: str) -> str:
    quoted_str = quote(string)
    return (
        "https://bloom.neo4j.io/index.html?connectURL="
        "neo4j%2Bs%3A//351463fc.databases.neo4j.io"
        f"&search={quoted_str}&run=true"
    )


##############################################################
# Graph/DB helper functions (kept because easy_query_author/chain needs them)
##############################################################

def draw_preview_graph(pivot, incoming_rels_df, outgoing_rels_df, graph_fmt):
    # URLs were shown in the original but commented out; keep computation harmlessly.
    _ = neo4j_url(pivot)
    _ = neo4j_url("local graph of " + pivot)

    preview_graph = graphviz.Digraph(format="png", engine=graph_fmt)
    preview_graph.node_attr["fixedsize"] = "true"
    preview_graph.node_attr["width"] = "2"

    preview_graph.node("\n".join(str(pivot).split(" ")), shape="doublecircle")
    for _, row in outgoing_rels_df.iterrows():
        preview_graph.node("\n".join(str(row["to"]).split(" ")), shape="circle")
        preview_graph.edge(
            "\n".join(str(pivot).split(" ")),
            "\n".join(str(row["to"]).split(" ")),
            label=str(row["type"]),
        )
    for _, row in incoming_rels_df.iterrows():
        preview_graph.node("\n".join(str(row["from"]).split(" ")), shape="circle")
        preview_graph.edge(
            "\n".join(str(row["from"]).split(" ")),
            "\n".join(str(pivot).split(" ")),
            label=str(row["type"]),
        )

    preview_graph.render("./result/preview")
    image = Image.open("./result/preview.png")
    st.image(image)


def get_author_info(author_id: str):
    proc = subprocess.run(
        f"ruby ./getSSauthor_info.rb {author_id}",
        shell=True,
        capture_output=True,
        text=True,
    )
    for paper in proc.stdout.splitlines()[3:]:
        st.write(f" {paper.replace('SS ', '・')}")


def next_types(name: str):
    outgoing_rel_list = st.session_state.rels_w_type_df[st.session_state.rels_df["from"] == name]
    incoming_rel_list = st.session_state.rels_w_type_df[st.session_state.rels_df["to"] == name]
    outgoing_types = outgoing_rel_list["to_type"].to_list()
    incoming_types = incoming_rel_list["from_type"].to_list()
    return outgoing_types + incoming_types


def next_relations(name: str):
    outgoing_rel_list = st.session_state.rels_w_type_df[st.session_state.rels_df["from"] == name]
    incoming_rel_list = st.session_state.rels_w_type_df[st.session_state.rels_df["to"] == name]
    outgoing_rel_types = outgoing_rel_list["type"].to_list()
    incoming_rel_types = incoming_rel_list["type"].to_list()
    return outgoing_rel_types + incoming_rel_types


def get_target_info(target: str) -> str:
    # summary_entries were not used in the original function (empty DF), keep same behavior.
    target_summary = ""
    if target != "":
        if re.match(r".+, [0-9]{5,}$", target):
            target_type = "author"
        else:
            target_type = (
                st.session_state.entries_df[st.session_state.entries_df["name"] == target]
                .iloc[0]["type"]
            )
    else:
        target_type = ""
    return "- " + target + " **" + target_type + "** " + target_summary


def candidate_types_and_relations(item):
    if item in rel_list:
        candidate_types = to_candidate_types[item]
        candidate_relations = []
    elif item in rel_list_reverse:
        candidate_types = from_candidate_types[orig_rel(item)]
        candidate_relations = []
    elif item in entry_super_types:
        candidate_relations_outgoing = list(filter(lambda r: item in from_candidate_types[r], rel_list))
        candidate_relations_incoming = list(filter(lambda r: item in to_candidate_types[r], rel_list))
        candidate_relations = candidate_relations_outgoing + list(
            map(lambda r: reverse_rel(r), candidate_relations_incoming)
        )
        candidate_types_outgoing = reduce(
            lambda a, b: a + b, list(map(lambda r: to_candidate_types[r], candidate_relations_outgoing)), []
        )
        candidate_types_incoming = reduce(
            lambda a, b: a + b, list(map(lambda r: from_candidate_types[r], candidate_relations_incoming)), []
        )
        candidate_types = candidate_types_outgoing + candidate_types_incoming
    elif item in entry_name_list:
        candidate_types = next_types(item)
        candidate_relations = next_relations(item)
    else:
        candidate_types = []
        candidate_relations = []
    return [candidate_types, candidate_relations]


##############################################################
# The 4 tabs used by the "本体" section
##############################################################

@st.fragment
def easy_query_phen_hyp():
    cols_easy = st.columns(2)
    with cols_easy[0]:
        key_entry_names = st.multiselect(
            "現象・仮説・枠組名:",
            ["polarity sensitivity"]
            + topic_entry_name_list
            + hypothesis_entry_name_list
            + framework_entry_name_list,
        )
    with cols_easy[1]:
        target_node_type = st.selectbox("エントリの種類:", entry_super_types)
        easy_path_length = st.select_slider("距離", options=range(1, 11), value=3)

    st.markdown(
        f'現象・仮説・枠組「{", ".join(key_entry_names)}」と関連する{target_node_type}エントリを検索'
    )

    if "easy_query_list" not in st.session_state:
        st.session_state.easy_query_list = []

    cols_easy_buttons = st.columns(4)
    with cols_easy_buttons[0]:
        if st.button("クエリ追加"):
            new_query = format_easy_query(key_entry_names, target_node_type, easy_path_length)
            st.session_state.easy_query_list = [new_query] + st.session_state.easy_query_list
    with cols_easy_buttons[1]:
        if st.button("クエリ消去"):
            st.session_state.easy_query_list = []

    easy_query = "\nunion\n".join(st.session_state.easy_query_list)
    easy_query_edited = st.text_area("クエリ:", easy_query, height=150)

    st.link_button("グラフ検索 (本システム)", neovis_url + quote(easy_query_edited))


@st.fragment
def easy_query_author():
    easy_author_name_id = st.selectbox("著者名:", author_entry_name_list).split(", ")
    easy_author_name = easy_author_name_id[0]
    easy_author_id = easy_author_name_id[1]

    if st.button("直近5件の論文を表示 (Semantic Scholar)"):
        get_author_info(easy_author_id)

    with st.expander("周辺ノード (1ホップ)"):
        graph_search_author_incoming_rels_df = st.session_state.rels_df[
            st.session_state.rels_df["to"] == easy_author_id
        ]
        graph_search_author_outgoing_rels_df = st.session_state.rels_df[
            st.session_state.rels_df["from"] == easy_author_id
        ]
        gsearch_tab1, gsearch_tab2 = st.tabs(["グラフ表示", "リスト表示"])
        with gsearch_tab1:
            draw_preview_graph(
                easy_author_id,
                graph_search_author_incoming_rels_df,
                graph_search_author_outgoing_rels_df,
                "circo",
            )
        with gsearch_tab2:
            st.write("incoming:")
            st.write(graph_search_author_incoming_rels_df)
            st.write("outgoing:")
            st.write(graph_search_author_outgoing_rels_df)

    easy_author_option = st.selectbox(
        "選択肢:",
        [
            f'1. 著者「{easy_author_name}」の文献と (何らかの点で) 対立関係にある文献を検索',
            f'2. 著者「{easy_author_name}」の文献と (何らかの点で) 同意している文献を検索',
            f'3. 著者「{easy_author_name}」の文献と同じ現象を扱っている文献を検索',
        ],
    ).split(". ")[0]

    if "easy_query_author_list" not in st.session_state:
        st.session_state.easy_query_author_list = []

    cols_easy_buttons = st.columns(4)
    with cols_easy_buttons[0]:
        if st.button("クエリ追加", key="easy_author_add"):
            if easy_author_option == "1":
                new_easy_query = format_easy_query_author_disagree(easy_author_id)
            elif easy_author_option == "2":
                new_easy_query = format_easy_query_author_agree(easy_author_id)
            else:
                new_easy_query = format_easy_query_author_same_topic(easy_author_id)
            st.session_state.easy_query_author_list = [new_easy_query] + st.session_state.easy_query_author_list
    with cols_easy_buttons[1]:
        if st.button("クエリ消去", key="easy_author_delete"):
            st.session_state.easy_query_author_list = []

    easy_query_author = "\nunion\n".join(st.session_state.easy_query_author_list)
    easy_query_author_edited = st.text_area("クエリ:", easy_query_author, height=150, key="easy_author_text_area")

    st.link_button("グラフ検索 (本システム)", neovis_url + quote(easy_query_author_edited))


@st.fragment
def easy_query_chain():
    query_candidate_list = (
        ["ANY"]
        + entry_name_list
        + entry_super_types * 10
        + entry_types * 10
        + rel_list * 10
        + rel_list_reverse * 10
    )
    query_chain_info_container = st.container()
    query_chunk = st.multiselect("クエリ:", query_candidate_list)

    # Ensure rels_w_type_df is available for candidate recommendation.
    st.session_state.rels_w_type_df = load_rels_w_type()

    with query_chain_info_container:
        if query_chunk != []:
            last_node = query_chunk[-1]
            if last_node in entry_name_list:
                st.write("現在の要素 " + get_target_info(last_node))
            candidate_types, candidate_relations = candidate_types_and_relations(last_node)
            st.write("タイプ候補: " + ", ".join(set(candidate_types)))
            st.write("関係名候補: " + ", ".join(set(candidate_relations)))

    query_chain_text = format_query_chain_alt(query_chunk)
    if st.button("クエリ消去", key="query_chain_delete"):
        query_chain_text = ""
    query_body = f"match p = {query_chain_text} return *, relationships(p)"
    query_chain_text_edited = st.text_area("cypher式:", query_body, height=50)
    st.link_button("グラフ検索 (本システム)", neovis_url + quote(query_chain_text_edited))


@st.fragment
def easy_query_path():
    st.markdown("任意の二つのノードがつながるかどうかを検索します。")
    pf_candidate_list = ["ANY"] + entry_name_list + entry_super_types + rel_list + rel_list_reverse
    cols_pf = st.columns(3)
    with cols_pf[0]:
        pf_from = st.selectbox("from:", pf_candidate_list)
    with cols_pf[2]:
        pf_length = st.selectbox("length:", range(1, 5))
    with cols_pf[1]:
        pf_to = st.selectbox("to:", pf_candidate_list)

    pf_query = (
        f"match p = {format_node(pf_from)}-[*..{pf_length}]-{format_node(pf_to)} "
        "return *, relationships(p)"
    )
    st.link_button("グラフ検索 (本システム)", neovis_url + quote(pf_query))


##############################################################
# 本体 (kept)
##############################################################

st.title('GrammarXivグラフ検索ツール')

get_relation_completion = st.button("補完候補をアップデート")

if get_relation_completion:
    subprocess.run("ruby ./read_entries.rb", shell=True, text=True)

(
    easy_query_tab_phen_hyp,
    easy_query_tab_author,
    easy_query_tab_chain,
    easy_query_tab_path,
) = st.tabs(["現象・仮説・枠組名から検索",
             "著者名から検索",
             "クエリ・チェーン",
             "パス検索"])

with easy_query_tab_phen_hyp:
    easy_query_phen_hyp()
with easy_query_tab_author:
    easy_query_author()
with easy_query_tab_chain:
    easy_query_chain()
with easy_query_tab_path:
    easy_query_path()




