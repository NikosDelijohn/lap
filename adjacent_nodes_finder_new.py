#!/usr/bin/python3 

from lark import Lark, Transformer, v_args
from dataclasses import dataclass
from copy import copy
import math
from typing import List, Dict, Tuple, Any, Union

import re 
import argparse

DEF_NET_GRAMMAR = r"""

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

@dataclass 
class RoutingPoint:
    first_coordinate: Union[int, str]
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
        >>> Lark(DEF_NET_GRAMMAR, parser='lalr', start='routing_point', transformer=DefNetsTransformer()).parse(data)
        (x,y) = 37050 359660
        >>> data = "( 37050 * 2 )"
        >>> Lark(DEF_NET_GRAMMAR, parser='lalr', start='routing_point', transformer=DefNetsTransformer()).parse(data)
        (x,y) = 37050 *
        >>> data = "( 37050 23245 )"
        >>> Lark(DEF_NET_GRAMMAR, parser='lalr', start='routing_point', transformer=DefNetsTransformer()).parse(data)
        (x,y) = 37050 23245
        """
        return RoutingPoint(int(first_coordinate) if first_coordinate != '*' else '*',
                            int(second_coordinate) if second_coordinate != '*' else '*')

    @v_args(inline=True)
    def routing_element(self, keyword:str, metal_layer: str, starting_point:RoutingPoint, ending_point: RoutingPoint = None, via: str = None ) -> RoutingElement:
        """
        >>> data = "ROUTED metal2 ( 37050 359660 ) ( * 361340 ) via1_4"
        >>> Lark(DEF_NET_GRAMMAR, parser='lalr', start='routing_element', transformer=DefNetsTransformer()).parse(data)
        metal2: (x,y) = 37050 359660 -> (x,y) = 37050 361340
        """
        if isinstance(ending_point, str):    
            return RoutingElement(metal_layer, ending_point, starting_point, None)
        else:
            return RoutingElement(metal_layer, via, starting_point, ending_point)
    
    def regular_wiring_statement(self, list_of_routes: List[RoutingElement]) -> List[RoutingElement]: 
        """
        >>> data = "+ ROUTED metal2 ( 37050 359660 ) ( * 361340 ) via1_4 NEW metal4 ( 261890 56420 ) ( 262450 * );"
        >>> Lark(DEF_NET_GRAMMAR, parser='lalr', start='regular_wiring_statement', transformer=DefNetsTransformer()).parse(data)
        [metal2: (x,y) = 37050 359660 -> (x,y) = 37050 361340, metal4: (x,y) = 261890 56420 -> (x,y) = 262450 56420]
        """
        return list_of_routes

    def pin_or_port(self, port: Port) -> Port: 
        """
        >>> data = "( PIN ram_cfg_i[9] )"
        >>> Lark(DEF_NET_GRAMMAR, parser='lalr', start='pin_or_port', transformer=DefNetsTransformer()).parse(data)
        ram_cfg_i[9]
        >>> data = "( u_ibex_core/ex_block_i/gen_multdiv_fast_multdiv_i/U1882 CO )"
        >>> Lark(DEF_NET_GRAMMAR, parser='lalr', start='pin_or_port', transformer=DefNetsTransformer()).parse(data)
        u_ibex_core/ex_block_i/gen_multdiv_fast_multdiv_i/U1882/CO
        """      
        return port 
    
    @v_args(inline=True)
    def pin(sef, pin_name: str) -> Port: 
        """
        >>> data = "( PIN ram_cfg_i[9] )"
        >>> Lark(DEF_NET_GRAMMAR, parser='lalr', start='pin_or_port', transformer=DefNetsTransformer()).parse(data)
        ram_cfg_i[9]
        """      
        return Port(None, pin_name)
    
    @v_args(inline=True)
    def port(self, hierarchy_name: str, port_name: str) -> Port: 
        """
        >>> data = "( u_ibex_core/ex_block_i/gen_multdiv_fast_multdiv_i/U1882 CO )"
        >>> Lark(DEF_NET_GRAMMAR, parser='lalr', start='pin_or_port', transformer=DefNetsTransformer()).parse(data)
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
        >>> Lark(DEF_NET_GRAMMAR, parser='lalr', start='net', transformer=DefNetsTransformer()).parse(data)
        u_ibex_core/ex_block_i/gen_multdiv_fast_multdiv_i/n1764: (308370,89180,310650,89180) -> (307810,124740,308370,124740) -> (308090,90580,308370,90580) -> (308370,89180) -> (308370,144060) -> (310650,86940)
        """      
        return Net(net_name, ports, elements)

    def port_list(self, ports: List[Port]) -> List[Port]:
        """
        >>> data = '''( u_ibex_core/ex_block_i/gen_multdiv_fast_multdiv_i/U1882 CO )
        ... ( u_ibex_core/ex_block_i/gen_multdiv_fast_multdiv_i/U1874 A )'''
        >>> Lark(DEF_NET_GRAMMAR, parser='lalr', start='port_list', transformer=DefNetsTransformer()).parse(data)
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
        >>> Lark(DEF_NET_GRAMMAR, parser='lalr', start='element_list', transformer=DefNetsTransformer()).parse(data) # doctest +NORMALIZE_WHITESPACE
        [metal3: (x,y) = 308370 89180 -> (x,y) = 310650 89180, metal4: (x,y) = 307810 124740 -> (x,y) = 308370 124740, metal4: (x,y) = 308090 90580 -> (x,y) = 308370 90580, metal4: (x,y) = 308370 89180, metal3: (x,y) = 308370 144060, metal2: (x,y) = 310650 86940]
        """
        return elements

    net_list = list
    
def parse(file_name:str, targeted_functional_unit:str=None) -> List[Net]:
    """
    this function accepts the .def file and targeted functional unit, and then generate a list containing
    parameters:
        - file_name: .def file or other text file
        - targeted_funtianl_unit: set filter, just perserve functional unit which we are interested in
    output:
        - nets_in_need: out put a net list that contains the intersted net objects

    >>> parse("_doctest_only.def", "decoder") # doctest: +ELLIPSIS
    [u_ibex_core/id_stage_i/decoder_i/n20: (95570,75180,95570,75740) -> (94050,75740,95570,75740) -> (95570,75180,96710,75180), \
u_ibex_core/id_stage_i/decoder_i/n21: (110390,118300,112290,118300) -> (109250,118300,110390,118300) -> (110390,118300) -> (112290,118300), \
u_ibex_core/id_stage_i/decoder_i/n22: (90630,97580,91770,97580) -> (89490,97580,90630,97580) -> (91770,97580,91770,98140), \
u_ibex_core/id_stage_i/decoder_i/n23: (87590,91700,89110,91700) -> (87400,92540,87590,92540) -> (86450,97300,87590,97300) -> (87400,92540,87400,96460) -> (87400,96460,87590,96460) -> (87590,91700,87590,92540) -> (87590,96460,87590,97300) -> (87970,78820,89110,78820) -> (89110,78820,89110,91700) -> (89110,91700,91770,91700) -> (91770,90020,91770,91700) -> (87590,91700) -> (91770,90020)]
    """

    try: 
        with open(file_name, "r") as input_file:
            data = input_file.read()
    except OSError: 
        exit(f"Unable to open file \"{file_name}\" for reading.")
    
    match = re.search(r'\bNETS\b\s+\d+\s*;(.*)\bEND NETS\b', data, re.DOTALL | re.MULTILINE)
    
    if not match:
        raise ValueError("Invalid input file")

    data = match.group(1)

    net_parser = Lark(DEF_NET_GRAMMAR, parser='lalr', start='net_list', transformer=DefNetsTransformer())
    net_data = net_parser.parse(data)

    # extract nodes that are needed
    nets_in_need = [ net for net in net_data if targeted_functional_unit in net.net_name ]

    assert (len(nets_in_need) > 0), f"Unable to extract nets in unit {targeted_functional_unit}"

    return nets_in_need

def find_nearest_neighbour_for_net(net: Net, functional_node_list: List[Net]) -> Tuple[Net, str]:
    """
    this function accepts target net and a netlist to search for the nearest net in it and also return distances and their metal layer
    parameters: 
        - net: target net
        - functional_node_list: nets search space
    ouput:
        - net: closest net.
        - metal_layer: the metal layer of target net and its closest net.

    >>> net_name1="u_ibex_core/id_stage_i/decoder_i/n1"
    >>> routing_ports1=[]
    >>> routing_elements1=[RoutingElement('metal1', 'via1', RoutingPoint(0, 1), RoutingPoint(1, 1)), RoutingElement('metal2', None, RoutingPoint(0, 1), RoutingPoint(0, 0))]
    >>> net_name2="u_ibex_core/id_stage_i/decoder_i/n2"
    >>> routing_ports2=[]
    >>> routing_elements2=[RoutingElement('metal1', 'via2', RoutingPoint(0, 2), RoutingPoint(2, 2)), RoutingElement('metal1', None, RoutingPoint(2, 2), RoutingPoint(2, 4)), RoutingElement('metal1', None, RoutingPoint(2, 2), RoutingPoint(3, 2))]
    >>> net_name3="u_ibex_core/id_stage_i/decoder_i/n3"
    >>> routing_ports3=[]
    >>> routing_elements3=[RoutingElement('metal1', 'via1', RoutingPoint(2, 1), RoutingPoint(3, 1)), RoutingElement('metal1', None, RoutingPoint(3, 1), RoutingPoint(3, 0))]
    >>> net_name4="u_ibex_core/id_stage_i/decoder_i/n4"
    >>> routing_ports4=[]
    >>> routing_elements4=[RoutingElement('metal2', None, RoutingPoint(3, 2), RoutingPoint(3, 3)), RoutingElement('metal2', None, RoutingPoint(3, 3), RoutingPoint(2, 3))]
    >>> net_name5="u_ibex_core/id_stage_i/decoder_i/n5"
    >>> routing_ports5=[]
    >>> routing_elements5=[RoutingElement('metal1', 'via1', RoutingPoint(0, 1), RoutingPoint(1, 1)), RoutingElement('metal1', None, RoutingPoint(0, 1), RoutingPoint(0, 0))]
    >>> net1=Net(net_name1, routing_ports1, routing_elements1)
    >>> net2=Net(net_name2, routing_ports2, routing_elements2)
    >>> net3=Net(net_name3, routing_ports3, routing_elements3)
    >>> net4=Net(net_name4, routing_ports4, routing_elements4)
    >>> net5=Net(net_name5, routing_ports5, routing_elements5)
    >>> net_lst=[net1, net2, net3, net4, net5]
    >>> find_nearest_neighbour_for_net(net1, net_lst)
    (u_ibex_core/id_stage_i/decoder_i/n2: (0,2,2,2) -> (2,2,2,4) -> (2,2,3,2), 'metal1')
    >>> find_nearest_neighbour_for_net(net2, net_lst)
    (u_ibex_core/id_stage_i/decoder_i/n1: (0,1,1,1) -> (0,1,0,0), 'metal1')
    >>> find_nearest_neighbour_for_net(net3, net_lst)
    (u_ibex_core/id_stage_i/decoder_i/n1: (0,1,1,1) -> (0,1,0,0), 'metal1')
    >>> find_nearest_neighbour_for_net(net4, net_lst)
    (u_ibex_core/id_stage_i/decoder_i/n4: (3,2,3,3) -> (3,3,2,3), 'metal2')
    >>> find_nearest_neighbour_for_net(net5, net_lst)
    """
    other_nets_in_same_layer = list() 

    for n in functional_node_list:
        if n.routing_elements[0].metal_layer == net.routing_elements[0].metal_layer \
            and functional_node_list.index(n) != functional_node_list.index(net):
            other_nets_in_same_layer.append(n)
    
    # No other nets exist in the same metal layer. Consider the same net twice.
    if len(other_nets_in_same_layer) == 0:
        return net, net.routing_elements[0].metal_layer

    starting_point_distance_from_net = lambda other_net: math.dist(
        [net.routing_elements[0].starting_point.first_coordinate, \
        net.routing_elements[0].starting_point.second_coordinate], \
        [other_net.routing_elements[0].starting_point.first_coordinate, \
        other_net.routing_elements[0].starting_point.second_coordinate])

    nearest_node = min(other_nets_in_same_layer, key = starting_point_distance_from_net)

    assert nearest_node.routing_elements[0].metal_layer == net.routing_elements[0].metal_layer, "Nets on different metal layers!"
    return nearest_node, nearest_node.routing_elements[0].metal_layer

def main():

    net_list = parse(cli_arguments.def_file_name, cli_arguments.functional_unit)
    
    # filter unrouted nets
    net_list = list(filter(lambda net : len(net.routing_elements) > 0, net_list))

    neighbouring_nets = list()
    for net in net_list:         
        closest_net, metal_layer = find_nearest_neighbour_for_net(net, net_list)
        pair = f"{net.net_name},{closest_net.net_name}"

        # For a combination 'a,b' checks whether 'b,a' exists already. 
        if ','.join(pair.split(',')[::-1]) in neighbouring_nets: 
            continue
        
        neighbouring_nets.append(f"{pair},{metal_layer}")

    # write to output file
    with open(cli_arguments.output_file, "w") as output:
        for pair in neighbouring_nets:
            output.write(f"{pair}\n")
        
if __name__=="__main__":

    param_parser=argparse.ArgumentParser()

    param_parser.add_argument("-u","--functional_unit", action = "store", help = "Specifies the targeted functional unit", required = True)
    param_parser.add_argument('-f', "--def_file_name", action = 'store', help = "Input .def file", required = True, metavar = "xxx.def")  
    param_parser.add_argument('-o','--output_file', action = 'store', help = "Output file 'xxx.map' ", default = "pair.map", metavar = "xxx_pair.map")    
    
    cli_arguments = param_parser.parse_args()

    main()


