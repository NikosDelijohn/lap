'''
@ Author: ZhouCH
@ Date: Do not edit
LastEditors: Please set LastEditors
LastEditTime: 2023-02-19 01:44:30
@ FilePath: Do not edit
@ Description: 
@ License: MIT
'''

from lark import Lark
import math
from typing import List, Dict, Tuple

node_list=[] #contains all the node in the SoC

class soc_node:
    layout=[]
    location=[0,0]

def sorting(node:soc_node)->soc_node:

    # finding all the node in the same layout
    node_in_same_layout_list=[]
    for n in node_list:
        if n.layout==node.layout:
            node_in_same_layout_list.append([n, 0])

    # calculate euclidean distances between node and other nodes
    for ele in node_in_same_layout_list:
        ele[1]=math.dist(ele[0].location, n.location)

    # bubble sorting their euclidean distances
    # TODO: sorting algorithm

    return node_in_same_layout_list[0][0]

def file_sparser(file_name:str) -> List[soc_node]:
    all_node=[]

    # read the file which is our target
    with open(file_name, "r") as input_file:
        data = input_file.read()
    net_input = data[data.find("NETS") + 4 : data.find("END NETS")]
    # TODO: sparse the doc.def and get all the useful information of each node
    
    return all_node

def main():
    node_list=file_sparser("ibex_top_working.def")
    
        



if __name__=="__main__":
    main()

