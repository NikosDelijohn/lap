# coding=utf-8

'''
@ Author: ZhouCH
@ Date: Do not edit
LastEditors: Please set LastEditors
LastEditTime: 2023-02-25 23:06:43
@ FilePath: Do not edit
@ Description: 
@ License: MIT
'''

from lark import Lark
from lark import Transformer
import math
from typing import List, Dict, Tuple, Any
import random
import sys
import argparse as ap

functional_unit_list={"adder":"u_ibex_core/ex_block_i/alu_i/alu_32bit_adder/",
                 "lsu":"u_ibex_core/load_store_unit_i/",
                 "compressed_decoder":"u_ibex_core/if_stage_i/compressed_decoder_i/",
                 "decoder":"u_ibex_core/id_stage_i/decoder_i/"}

node_list=[] #contains all the node in the SoC

net_grammar=r"""
    net_list: net*

    net: "-" net_name ["(" "PIN" pin_name ")"] net_aliasing_list ["+" regular_wiring_statement] ";"
    net_name: /(\w|\/|\[|\])+/
    pin_name: /(\w)+\[[0-9]+\]/

    //net_name_alias
    net_aliasing_list: net_name_alias*
    net_name_alias: "(" component_path net_alias ")"
    component_path: /(\w|\/)+/
    net_alias: CNAME

    regular_wiring_statement: (wire)+ 
    wire: WIRE_TYPE layer "(" x y EXT_VAL? ")" ["(" x_ y_ EXT_VAL_? ")"] [via_name]  
    WIRE_TYPE: ("ROUTED"|"NEW")~1
    layer: CNAME
    x: NUMBER
    y: NUMBER
    EXT_VAL: NUMBER
    x_: NUMBER|/\*/
    y_: NUMBER|/\*/
    EXT_VAL_: NUMBER
    via_name: CNAME

    %import common.SIGNED_NUMBER    
    %import common.NUMBER           
    %import common.CNAME            
    %import common.WS
    %ignore WS
    """

class soc_node:
    name=None
    layout=None
    location=[0,0]

    def __init__(self, name, layout, location) -> None:
        self.name=name
        self.layout=layout
        self.location=location
    
    def check_name(self):
        print(self.name)

    def check_layout(self):
        print(self.layout)

    def check_location(self):
        print(f"###############################")
        print(f"x={self.location[0]}")
        print(f"y={self.location[1]}")

# {net_name: [pin_name, aliasing_dict{component: alias}, wire_list[[wire_type, layer, start_point], ...]], ...}
class data_transformer(Transformer):
    def net_list(self, nets):
        return dict(nets)
    
    def net(self, net_info):
        net_name, other_info=net_info[0], net_info[1:]
        return net_name, other_info
    
    def net_name(self, name):
        return str(name[0])
    
    def pin_name(self, name):
        return str(name[0])
    
    def net_aliasing_list(self, alias_list):
        return dict(alias_list)
    
    def net_name_alias(self, alias_pair):
        path, name=alias_pair[0], alias_pair[1] 
        return path, name
        
    def component_path(self, path):
        return str(path[0])

    def net_alias(self, name):
        return str(name[0])
    
    def regular_wiring_statement(self, wire_list):
        return list(wire_list)
    
    def wire(self, wire_info):
        tp, layer, coordinate=wire_info[0], wire_info[1], [wire_info[2], wire_info[3]]
        return tp, layer, coordinate
    
    def WIRE_TYPE(self, tp):
        return str(tp)
    
    def layer(self, l):
        return str(l[0])
    
    def x(self, n):
        return str(n[0])
    
    def y(self, n):
        return str(n[0])

def sorting(node:soc_node, functional_node_list:list)->Tuple[soc_node, float]:
    # finding all the node in the same layout.
    node_in_same_layout_list=[]

    for n in functional_node_list:
        if n.layout==node.layout:
            node_in_same_layout_list.append(n) #[another node, distance to a specified node]
    node_in_same_layout_list.remove(node) # remove node itself

    # calculate euclidean distances between node (wire starting point) and other nodes (starting point)
    nearest_node=node_in_same_layout_list[0]
    distance=math.dist([float(x) for x in nearest_node.location], [float(x) for x in node.location])

    for ele in node_in_same_layout_list[1:]:
        cur_dis=math.dist([float(x) for x in ele.location], [float(x) for x in node.location])
        if cur_dis<=distance:
            nearest_node=ele
            distance=cur_dis

    return nearest_node, distance

def file_parser(file_name:str, targeted_functional_unit:str=None) -> List[soc_node]:
    all_node={}

    # read the file which is our target
    with open(file_name, "r") as input_file:
        data = input_file.read()
    net_input = data[data.find("NETS") + 13 : data.find("END NETS")]
    
    # parse the doc.def and get all the useful information of each node
    net_parser = Lark(net_grammar, start='net_list')
    net_data = net_parser.parse(net_input)

    # transform data to a dictionary
    all_node=data_transformer().transform(net_data)
    # print(all_node)
    # print(targeted_functional_unit)
    
    # extract nodes that are needed
    node_in_need_dict={}
    if targeted_functional_unit!=None and targeted_functional_unit in functional_unit_list.keys():
        for node_name, node_info in all_node.items():
            if functional_unit_list[targeted_functional_unit] in node_name:
                node_in_need_dict[node_name]=node_info
    else:
        print("\033[31m[warning]\033[0m you didn't specify any available functional unit!")
        node_in_need_dict=all_node

    # here is aiming at extract the first wire and its info, and bind them with a node. 
    node_in_need=[]
    for node_name, node_info in node_in_need_dict.items():
        if node_info[2]==None:
            node_obj=soc_node(node_name, None, [0,0] )
        else:
            node_obj=soc_node(node_name, node_info[2][0][1], node_info[2][0][2] )
        node_in_need.append(node_obj)
    return node_in_need

def main():
    param_parser=ap.ArgumentParser(
        prog="adjacent_nodes_finder.py",
        description="This file is intended to parse the NETS segment of the '.def' file. \
            It accepts the name of target functional unit to filter other unexpected nodes",
        epilog=None
    )

    param_parser.add_argument("-fu","--functional_unit",
                                action="store",
                                choices=["adder", "decoder", "compressed_decoder", "lsu"],
                                help="This argument specifies the targeted functional unit, \
                                    if 'None' is the param, the program will add all the nodes of the processor.",
                                required=False
                                )
    param_parser.add_argument('-f', "--file_name",
                                action='store',
                                help="This argument indicates a 'xxx.def' file, or a text file with NETS segment.",
                                required=True,
                                metavar="xxx.def"
                                )  
    param_parser.add_argument('-of','--output_file',
                                action='store',
                                help="this argument indicetes the output file 'xxx.map' of the program, \
                                default value is 'pair.map'",
                                default="pair.map",
                                metavar="xxx_pair.map")    
    args=param_parser.parse_args()
    
    print("#######################")
    print("##  \033[33mPROGRAM START\033[0m:   ##")
    print("#######################")

    # node_list=file_parser("ibex_top_working.def")
    node_list=file_parser(args.file_name, args.functional_unit)

    # create pairs
    pair_list=[]
    for node in node_list:         
        # get net couple
        n1= node
        n2= sorting(n1, node_list)[0]
        pair=[n1.name, n2.name]
        # check if there are any repeated pairs in the list
        indicator=0
        for p in pair_list:
            if set(pair)==set(p):
                indicator=1
        if len(pair_list)==0 or indicator==0:
            pair_list.append(pair)
    
    # write to output file
    with open(args.output_file, "w") as output:
        for pair in pair_list:
            output.write(f"{pair[0]};{pair[1]}\n")
        
if __name__=="__main__":
    main()

