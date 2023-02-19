'''
@ Author: ZhouCH
@ Date: Do not edit
LastEditors: Please set LastEditors
LastEditTime: 2023-02-19 11:45:10
@ FilePath: Do not edit
@ Description: 
@ License: MIT
'''

from lark import Lark
import math
from typing import List, Dict, Tuple
import random
import os
import sys

node_list=[] #contains all the node in the SoC

net_grammar = r"""
    start: net*

    net: "-" net_name net_name_alias* "+" regular_wiring_statement* ";"

    regular_wiring_statement: .......

    net_name_alias: "(" net_name ")"

    net_name: ESCAPED_STRING

    %import common.ESCAPED_STRING
    %import common.SIGNED_NUMBER
    %import common.WS
    %ignore WS
    """

class soc_node:
    layout=[]
    location=[0,0]

def sorting(node:soc_node)->List[soc_node,float]:

    # finding all the node in the same layout.
    node_in_same_layout_list=[]
    for n in node_list:
        if n.layout==node.layout:
            node_in_same_layout_list.append([n, 0]) #[another node, distance to a specified node]
    node_in_same_layout_list.remove([node, 0]) # remove node itself

    # calculate euclidean distances between node£¨wire starting point£©and other nodes£¨starting point£©
    # TODO: we should calculate the nearest distance between two broken lines
    nearest_node=node_in_same_layout_list[0]
    distance=math.dist(node_in_same_layout_list[0].location, node.location)
    for ele in node_in_same_layout_list[1:]:
        ele[1]=math.dist(ele[0].location, node.location)
        if ele[1]<=distance:
            nearest_node=ele[0]
            distance=ele[1]

    return [nearest_node,distance]

def file_sparser(file_name:str, node_map:str) -> List[soc_node]:
    all_node=[]

    # read the file which is our target
    with open(file_name, "r") as input_file:
        data = input_file.read()
    net_input = data[data.find("NETS") + 4 : data.find("END NETS")]
    # TODO: sparse the doc.def and get all the useful information of each node
    net_parser = Lark(net_grammar, start='value', parser='lalr')
    net_data = net_parser.parse(net_input)
    
    return all_node

def main():
    print("argv[1] is the functional unit's node map, eg.'adder.map' ")
    node_list=file_sparser("ibex_top_working.def", sys.argv[1])

    # create pairs
    with open(sys.argv[1], "w") as output:
        while len(node_list)>0:
            # get net couple
            if len(node_list)%2==0:
                pair=random.sample(node_list, 2)
                node_list.remove(pair[0])
                node_list.remove(pair[1])
            elif len(node_list)%2==1:
                pair=random.sample(node_list, 3)
                node_list.remove(pair[0])
                node_list.remove(pair[1])
                node_list.remove(pair[2])
            
            # parse pair string
            p_lst=[]
            for p in pair:    
                p_lst.append(p.rstrip("\n"))
                print(p_lst)
            
            if len(p_lst)==2:
                output.write("{};{}\n".format(p_lst[0], p_lst[1]))
            elif len(p_lst)==3:
                output.write("{};{};{}\n".format(p_lst[0], p_lst[1], p_lst[2]))
        
if __name__=="__main__":
    main()

