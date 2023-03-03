# coding=utf-8

'''
@ Author: ZhouCH
@ Date: Do not edit
LastEditors: Please set LastEditors
LastEditTime: 2023-03-03 21:44:52
@ FilePath: Do not edit
@ Description: 
@ License: MIT
'''

from lark import Lark, Transformer, v_args
from dataclasses import dataclass
from copy import copy, deepcopy
import math
from typing import List, Dict, Tuple, Any, Union
import random
import sys
import re 
import argparse as ap

functional_unit_list={"adder":"u_ibex_core/ex_block_i/alu_i/alu_32bit_adder/",
                 "lsu":"u_ibex_core/load_store_unit_i/",
                 "compressed_decoder":"u_ibex_core/if_stage_i/compressed_decoder_i/",
                 "decoder":"u_ibex_core/id_stage_i/decoder_i/"}

net_list=[] #contains all the node in the SoC
#
net_grammar=r"""

    net_list: net+

    net: "-" NET_NAME port_list element_list ";" 
    ?port_list: pin_or_port+
    ?element_list: regular_wiring_statement*
    NET_NAME: /[^\s]+/ 

    ?pin_or_port: "(" (pin | port) ")"
    pin: "PIN" PIN_NAME
    port: COMPONENT_NAME PIN_NAME 

    PIN_NAME: /[^\s]+/
    COMPONENT_NAME: /(?!PIN)[^\s]+/

    regular_wiring_statement: "+" routing_element+
    routing_element: WIRING_KEYWORD LAYER_NAME routing_point routing_point? VIA_NAME?
    routing_point: "(" COORDINATE COORDINATE EXTENSION? ")" 
    WIRING_KEYWORD: "COVER" | "FIXED" | "ROUTED" | "NOSHIELD" | "NEW"  
    VIA_NAME: /(?!NEW)[^\s]+/
    EXTENSION: /\d+/
    COORDINATE: /\d+/ | "*"
    LAYER_NAME: /\w+\d+/

    %import common.SIGNED_NUMBER    
    %import common.NUMBER           
    %import common.CNAME            
    %import common.WS
    %ignore WS
    """

@dataclass # 创建_init_构造函数，并且将其所有的成员函数设置为类的初始化参数
class RoutingPoint:
    first_coordinate: Union[int, str] # 这个Union表示类型可能是int或者str
    second_coordinate: Union[int, str]  

    def __repr__(self) -> str:
        return f"(x,y) = {self.first_coordinate} {self.second_coordinate}"

@dataclass 
class RoutingElement: 
    metal_layer: str
    via: str 
    starting_point: RoutingPoint
    ending_point: RoutingPoint

    def normalize(self) -> "RoutingElement":
        if self.ending_point is None: 
            return self 
    
        starting_point = copy(self.starting_point)
        ending_point = copy(self.ending_point)
   
        if starting_point.first_coordinate == '*':
            starting_point.first_coordinate = ending_point.first_coordinate
        if starting_point.second_coordinate == '*':
            starting_point.second_coordinate = ending_point.second_coordinate

        if ending_point.first_coordinate == '*':
            ending_point.first_coordinate = starting_point.first_coordinate
        if ending_point.second_coordinate == '*':
            ending_point.second_coordinate = starting_point.second_coordinate

        return RoutingElement(self.metal_layer, self.via, starting_point, ending_point)

    def __repr__(self) -> str:
        if self.ending_point is None: 
            return f"{self.metal_layer}: {self.starting_point}"

        normalized = self.normalize()
        return f"{self.metal_layer}: {normalized.starting_point} -> {normalized.ending_point}"

@dataclass
class Port:
    hierarchy_name: str
    port: str 

    def __repr__(self) -> str:
        if self.hierarchy_name: 
            return f"{self.hierarchy_name}/{self.port}"
        else: 
            return f"{self.port}"

@dataclass 
class Net: 
    net_name: str 
    routing_ports: List[Port]
    routing_elements: List[RoutingElement]

    def __repr__(self) -> str:

        def _compact_routing_element(element: RoutingElement) -> str:
            normalized = element.normalize()
            start = normalized.starting_point

            if normalized.ending_point:
                end = normalized.ending_point
                return f"({start.first_coordinate},{start.second_coordinate},{end.first_coordinate},{end.second_coordinate})"
            else: 
                return f"({start.first_coordinate},{start.second_coordinate})"
            
        return f"{self.net_name}: {' -> '.join([_compact_routing_element(x) for x in self.routing_elements])}"
  

class DefNetsTransformer(Transformer):
    
    @v_args(inline=True) #
    def routing_point(self, first_coordinate: str, second_coordinate: str, extension: str = None) -> Any: 
        """
        >>> data = "( 37050 359660 2 )"
        >>> Lark(net_grammar, parser='lalr', start='routing_point', transformer=DefNetsTransformer()).parse(data)
        (x,y) = 37050 359660
        >>> data = "( 37050 * 2 )"
        >>> Lark(net_grammar, parser='lalr', start='routing_point', transformer=DefNetsTransformer()).parse(data)
        (x,y) = 37050 *
        >>> data = "( 37050 23245 )"
        >>> Lark(net_grammar, parser='lalr', start='routing_point', transformer=DefNetsTransformer()).parse(data)
        (x,y) = 37050 23245
        """
        return RoutingPoint(int(first_coordinate) if first_coordinate != '*' else '*',
                            int(second_coordinate) if second_coordinate != '*' else '*')

    @v_args(inline=True)
    def routing_element(self, keyword:str, metal_layer: str, starting_point:RoutingPoint, ending_point: RoutingPoint = None, via: str = None ) -> RoutingElement:
        """
        >>> data = "ROUTED metal2 ( 37050 359660 ) ( * 361340 ) via1_4"
        >>> Lark(net_grammar, parser='lalr', start='routing_element', transformer=DefNetsTransformer()).parse(data)
        metal2: (x,y) = 37050 359660 -> (x,y) = 37050 361340
        """
        if isinstance(ending_point, str):    
            return RoutingElement(metal_layer, ending_point, starting_point, None)
        else:
            return RoutingElement(metal_layer, via, starting_point, ending_point)
    
    def regular_wiring_statement(self, list_of_routes: List[RoutingElement]) -> List[RoutingElement]: 
        """
        >>> data = "+ ROUTED metal2 ( 37050 359660 ) ( * 361340 ) via1_4 NEW metal4 ( 261890 56420 ) ( 262450 * );"
        >>> Lark(net_grammar, parser='lalr', start='regular_wiring_statement', transformer=DefNetsTransformer()).parse(data)
        [metal2: (x,y) = 37050 359660 -> (x,y) = 37050 361340, metal4: (x,y) = 261890 56420 -> (x,y) = 262450 56420]
        """
        return list_of_routes

    def pin_or_port(self, port: Port) -> Port: 
        """
        >>> data = "( PIN ram_cfg_i[9] )"
        >>> Lark(net_grammar, parser='lalr', start='pin_or_port', transformer=DefNetsTransformer()).parse(data)
        ram_cfg_i[9]
        >>> data = "( u_ibex_core/ex_block_i/gen_multdiv_fast_multdiv_i/U1882 CO )"
        >>> Lark(net_grammar, parser='lalr', start='pin_or_port', transformer=DefNetsTransformer()).parse(data)
        u_ibex_core/ex_block_i/gen_multdiv_fast_multdiv_i/U1882/CO
        """      
        return port 
    
    @v_args(inline=True)
    def pin(sef, pin_name: str) -> Port: 
        """
        >>> data = "( PIN ram_cfg_i[9] )"
        >>> Lark(net_grammar, parser='lalr', start='pin_or_port', transformer=DefNetsTransformer()).parse(data)
        ram_cfg_i[9]
        """      
        return Port(None, pin_name)
    
    @v_args(inline=True)
    def port(self, hierarchy_name: str, port_name: str) -> Port: 
        """
        >>> data = "( u_ibex_core/ex_block_i/gen_multdiv_fast_multdiv_i/U1882 CO )"
        >>> Lark(net_grammar, parser='lalr', start='pin_or_port', transformer=DefNetsTransformer()).parse(data)
        u_ibex_core/ex_block_i/gen_multdiv_fast_multdiv_i/U1882/CO
        """      
        return Port(hierarchy_name, port_name)
    
    @v_args(inline=True)
    def net(self, net_name: str, ports: List[Port], elements: List[RoutingElement]) -> Net: 
        """
        >>> data = '''- u_ibex_core/ex_block_i/gen_multdiv_fast_multdiv_i/n1764
        ... ( u_ibex_core/ex_block_i/gen_multdiv_fast_multdiv_i/U1882 CO )
        ... ( u_ibex_core/ex_block_i/gen_multdiv_fast_multdiv_i/U1874 A )
        ... + ROUTED metal3 ( 308370 89180 ) ( 310650 * ) via2_5
        ...   NEW metal4 ( 307810 124740 ) ( 308370 * )
        ...   NEW metal4 ( 308090 90580 ) ( 308370 * )
        ...   NEW metal4 ( 308370 89180 ) via3_2
        ...   NEW metal3 ( 308370 144060 ) via2_5
        ...   NEW metal2 ( 310650 86940 ) via1_4
        ... ;'''
        >>> Lark(net_grammar, parser='lalr', start='net', transformer=DefNetsTransformer()).parse(data)
        u_ibex_core/ex_block_i/gen_multdiv_fast_multdiv_i/n1764: (308370,89180,310650,89180) -> (307810,124740,308370,124740) -> (308090,90580,308370,90580) -> (308370,89180) -> (308370,144060) -> (310650,86940)
        """      
        return Net(net_name, ports, elements)

    def port_list(self, ports: List[Port]) -> List[Port]:
        """
        >>> data = '''( u_ibex_core/ex_block_i/gen_multdiv_fast_multdiv_i/U1882 CO )
        ... ( u_ibex_core/ex_block_i/gen_multdiv_fast_multdiv_i/U1874 A )'''
        >>> Lark(net_grammar, parser='lalr', start='port_list', transformer=DefNetsTransformer()).parse(data)
        [u_ibex_core/ex_block_i/gen_multdiv_fast_multdiv_i/U1882/CO, u_ibex_core/ex_block_i/gen_multdiv_fast_multdiv_i/U1874/A]
        """    
        return ports 
    
    def element_list(self, elements: List[RoutingElement]) -> List[RoutingElement]:
        """
        >>> data = '''+ ROUTED metal3 ( 308370 89180 ) ( 310650 * ) via2_5
        ...   NEW metal4 ( 307810 124740 ) ( 308370 * )
        ...   NEW metal4 ( 308090 90580 ) ( 308370 * )
        ...   NEW metal4 ( 308370 89180 ) via3_2
        ...   NEW metal3 ( 308370 144060 ) via2_5
        ...   NEW metal2 ( 310650 86940 ) via1_4'''
        >>> Lark(net_grammar, parser='lalr', start='element_list', transformer=DefNetsTransformer()).parse(data) # doctest +NORMALIZE_WHITESPACE
        [metal3: (x,y) = 308370 89180 -> (x,y) = 310650 89180, metal4: (x,y) = 307810 124740 -> (x,y) = 308370 124740, metal4: (x,y) = 308090 90580 -> (x,y) = 308370 90580, metal4: (x,y) = 308370 89180, metal3: (x,y) = 308370 144060, metal2: (x,y) = 310650 86940]
        """        
        return elements

    net_list = list
    

def file_parser(file_name:str, targeted_functional_unit:str=None) -> Any:

    # read the file which is our target
    with open(file_name, "r") as input_file:
        data = input_file.read()
    #net_input = data[data.find("NETS") + 13 : data.find("END NETS")]
    
    match = re.search(r'\bNETS\b\s+\d+\s*;(.*)\bEND NETS\b', data, re.DOTALL | re.MULTILINE)
    
    if not match:
        raise ValueError("Invalid input file")

    print(data[:match.span(1)[0]].count('\n'))    
    data = match.group(1)

    net_parser = Lark(net_grammar, parser='lalr', start='net_list', transformer=DefNetsTransformer())
    net_data = net_parser.parse(data)
    
    # for net in net_data:
    #     print("+++++++++++++++++++++++++++++++++++++++")
    #     if (len(net.routing_elements)!=0):
    #         print(net.routing_elements[0])

    # exit(0)

    # extract nodes that are needed
    nets_in_need=[]
    if targeted_functional_unit!=None and targeted_functional_unit in functional_unit_list.keys():
        for net in net_data:
            if functional_unit_list[targeted_functional_unit] in net.net_name:
                nets_in_need.append(net)
    else:
        print("\033[31m[warning]\033[0m you didn't specify any available functional unit!")
        nets_in_need=net_data

    return nets_in_need

def sorting(net: Net, functional_node_list: List[Net])->Tuple[Net, float, str, str]:
    # finding all the node in the same layout.
    node_in_same_layout_list=[]

    for n in functional_node_list:
        if len(n.routing_elements)>0 and len(net.routing_elements)>0:
            if n.routing_elements[0].metal_layer==net.routing_elements[0].metal_layer:
                node_in_same_layout_list.append(n) 
    node_in_same_layout_list.remove(net) # remove node itself

    # calculate euclidean distances between node (wire starting point) and other nodes (starting point)
    nearest_node=node_in_same_layout_list[0]
    distance=math.dist([net.routing_elements[0].starting_point.first_coordinate,net.routing_elements[0].starting_point.second_coordinate], \
                        [nearest_node.routing_elements[0].starting_point.first_coordinate,nearest_node.routing_elements[0].starting_point.second_coordinate])

    for ele in node_in_same_layout_list[1:]:
        cur_dis=math.dist([net.routing_elements[0].starting_point.first_coordinate,net.routing_elements[0].starting_point.second_coordinate], \
                        [ele.routing_elements[0].starting_point.first_coordinate,ele.routing_elements[0].starting_point.second_coordinate])
        if cur_dis<=distance:
            nearest_node=ele
            distance=cur_dis

    return nearest_node, distance, net.routing_elements[0].metal_layer, nearest_node.routing_elements[0].metal_layer

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

    # net_list=file_parser("ibex_top_working.def")
    net_list=file_parser(args.file_name, args.functional_unit)

    # create pairs
    pair_list=[]
    for node in net_list:         
        # get net couple
        n1= node
        n2, distance, layer_n1, layer_n2 = sorting(n1, net_list)
        pair=[n1.net_name, n2.net_name, distance, layer_n1, layer_n2]
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
            output.write(f"{pair[0]};{pair[1]} , {pair[2]},{pair[3]},{pair[4]}\n")
        
if __name__=="__main__":
    main()

