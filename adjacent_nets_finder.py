#!/usr/bin/python3

from lark import Lark, Transformer, v_args
from dataclasses import dataclass
from copy import copy
from collections import defaultdict
from sklearn.neighbors import KDTree

import math
import numpy as np

from matplotlib import pyplot as plt

from typing import List, Dict, Tuple, Any, Union

import re
import tqdm
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
            return RoutingElement(metal_layer, ending_point, starting_point, None).normalize()
        else:
            return RoutingElement(metal_layer, via, starting_point, ending_point).normalize()

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

def plot_nets(nets: List[Net]) -> None:
    """
    >>> net_a = Net("net_a", [], [
    ...     RoutingElement('metal1', 'via2', RoutingPoint(0, 100), RoutingPoint(100, '*')),
    ...     RoutingElement('metal1', None, RoutingPoint(100, 100), RoutingPoint(200, '*')),
    ...     RoutingElement('metal1', None, RoutingPoint(200, 100), RoutingPoint('*', 0))])
    >>> net_b = Net("net_b", [], [
    ...     RoutingElement('metal1', 'via2', RoutingPoint(250, 150), RoutingPoint(300, '*')),
    ...     RoutingElement('metal1', None, RoutingPoint(300, 150), RoutingPoint(300, 400))])
    >>> net_c = Net("net_c", [], [
    ...     RoutingElement('metal1', 'via2', RoutingPoint(50, 80), RoutingPoint(90,80))])
    >>> #plot_nets([net_a, net_b, net_c])
    """

    metal_layers = {
        "metal1" : "blue",
        "metal2" : "red",
        "metal3" : "green",
        "metal4" : "cyan",
        "metal5" : "purple",
        "metal6" : "orange",
        "metal7" : "yellow",
        "metal8" : "magenta",
        "metal9" : "indigo",
        "metal10": "black"
    }

    for net in nets:

        for routing_element in net.routing_elements:

            if routing_element.ending_point is not None:
                plt.plot(
                    [routing_element.starting_point.first_coordinate, routing_element.ending_point.first_coordinate],
                    [routing_element.starting_point.second_coordinate, routing_element.ending_point.second_coordinate],
                    color = metal_layers[routing_element.metal_layer])
            else:
                plt.plot(routing_element.starting_point.first_coordinate, routing_element.starting_point.second_coordinate, color = metal_layers[routing_element.metal_layer])

    plt.show()


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
    stress_target_nets = [ net for net in net_data if targeted_functional_unit in net.net_name ]

    assert (len(stress_target_nets) > 0), f"Unable to extract nets in unit {targeted_functional_unit}"

    return stress_target_nets

def walk_routing_element(element: RoutingElement, step=10.0) -> List[RoutingPoint]:
    """ Walks the routing element from start to end and returns points on the element.
        Each point is in distance defined by the step parameter.
    >>> list(walk_routing_element(RoutingElement('metal1', None, RoutingPoint(32430, 324320), None)))
    [(x,y) = 32430 324320]
    >>> list(walk_routing_element(RoutingElement('metal1', None, RoutingPoint(32430, 324320), RoutingPoint(32490, '*'))))
    [(x,y) = 32430 324320, (x,y) = 32440 324320, (x,y) = 32450 324320, (x,y) = 32460 324320, (x,y) = 32470 324320, (x,y) = 32480 324320, (x,y) = 32490 324320]
    >>> list(walk_routing_element(RoutingElement('metal1', None, RoutingPoint(32430, 324330), RoutingPoint('*', 324320))))
    [(x,y) = 32430 324330, (x,y) = 32430 324320]
    """
    element = element.normalize()
    start = element.starting_point
    end = element.ending_point
    if end is None:
        yield element.starting_point
        return

    start = (start.first_coordinate, start.second_coordinate)
    end = (end.first_coordinate, end.second_coordinate)

    def _distance(start, end):
        return math.sqrt(math.pow(start[0] - end[0], 2.0) + math.pow(start[1] - end[1], 2.0))

    distance = _distance(start, end)
    difference = (end[0] - start[0], end[1] - start[1])
    direction = (difference[0] / max(0.001, distance), difference[1] / max(0.001, distance))

    yield element.starting_point
    current = start
    while True:
        current = (current[0] + step * direction[0], current[1] + step * direction[1])
        if _distance(start, current) >= distance:
            break
        yield RoutingPoint(int(current[0]), int(current[1]))
    yield element.ending_point

def points_per_metal_layer(net_list: List[Net], interpolate: bool = False) -> Tuple[dict,dict]:

    metal_layer_mapping = defaultdict(list)

    for net in net_list:
        for element in net.routing_elements:
            element = element.normalize()

            if not interpolate:
                points = [element.starting_point]
                if element.ending_point:
                    points += [element.ending_point]
            else:
                # In interpolation mode we walk the whole metal strip
                # and add multiple points in equidistant locations.
                points = walk_routing_element(element)

            for point in points:
                metal_layer_mapping[element.metal_layer] \
                    .append((net, point.first_coordinate, point.second_coordinate))


    np_compliant_dict = dict()
    kdtrees_per_layer = dict()

    for metal_layer, net_points in tqdm.tqdm(metal_layer_mapping.items()):

        np_compliant_dict[metal_layer] = np.empty((len(net_points),2))

        for index, (_, first_coordinate, second_coordinate) in enumerate(net_points):

            np_compliant_dict[metal_layer][index] = first_coordinate, second_coordinate

        kdtrees_per_layer[metal_layer] = KDTree(np_compliant_dict[metal_layer], metric="euclidean")

    return kdtrees_per_layer, metal_layer_mapping

def find_minimum_distance_across_layers(net: Net, KDtrees: Dict[str,KDTree], layer_mapping: dict, interpolate: bool = False) -> Tuple[Net,str]:
    """
    >>> net_a = Net("net_a", [], [
    ...     RoutingElement('metal1', 'via2', RoutingPoint(0, 100), RoutingPoint(100, '*')),
    ...     RoutingElement('metal1', None, RoutingPoint(100, 100), RoutingPoint(200, '*')),
    ...     RoutingElement('metal1', None, RoutingPoint(200, 0), RoutingPoint(0, 0))])
    >>> net_b = Net("net_b", [], [
    ...     RoutingElement('metal1', 'via2', RoutingPoint(250, 150), RoutingPoint(300, '*')),
    ...     RoutingElement('metal1', None, RoutingPoint(300, 150), RoutingPoint(300, 400))])
    >>> net_c = Net("net_c", [], [
    ...     RoutingElement('metal1', 'via2', RoutingPoint(50, 80), RoutingPoint(90,80))])
    >>> trees, mapping = points_per_metal_layer([net_a, net_b, net_c])
    >>> find_minimum_distance_across_layers(net_a, trees, mapping)
    (net_c: (50,80,90,80), 'metal1')
    >>> find_minimum_distance_across_layers(net_b, trees, mapping)
    (net_a: (0,100,100,100) -> (100,100,200,100) -> (200,0,0,0), 'metal1')
    >>> find_minimum_distance_across_layers(net_c, trees, mapping)
    (net_a: (0,100,100,100) -> (100,100,200,100) -> (200,0,0,0), 'metal1')
    """
    minimum_distance = np.inf
    minimum_distance_net_index = None
    minimum_distance_net_layer = None

    for routing_element in net.routing_elements:
        routing_element = routing_element.normalize()
        tree = KDtrees[routing_element.metal_layer]

        if not interpolate:
            points = [routing_element.starting_point]
            if routing_element.ending_point:
                points += [routing_element.ending_point]
        else:
            # In interpolation mode we walk the whole metal strip
            # and add multiple points in equidistant locations.
            points = walk_routing_element(routing_element)

        # For each point query the closest points that are not the net itself.
        for point in points:
            max_query_size = len(layer_mapping[routing_element.metal_layer])
            query_size = min(100, max_query_size)

            while query_size <= max_query_size:
                query_points = np.array([(point.first_coordinate, point.second_coordinate)])
                distances, indices = tree.query(query_points, k=query_size)
                for index, distance in zip(indices[0], distances[0]):
                    # Exclude the points of the net itself
                    if net.net_name == layer_mapping[routing_element.metal_layer][index][0].net_name:
                        continue

                    if distance < minimum_distance:
                        minimum_distance = distance
                        minimum_distance_net_index = index
                        minimum_distance_net_layer = routing_element.metal_layer

                if minimum_distance_net_index is not None:
                    break

                # We have exhausted all elements to match with.
                # There don't seem to exist other nets on this layer.
                if query_size == max_query_size:
                    break

                # Increase query size in case we have a lot of matches of the net with itself.
                query_size += 100
                query_size = min(query_size, max_query_size)
                continue

    assert (minimum_distance_net_index is not None), "There is no other net on this layer to match with"

    return layer_mapping[minimum_distance_net_layer][minimum_distance_net_index][0], minimum_distance_net_layer

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
    >>> routing_elements3=[RoutingElement('metal1', 'via3', RoutingPoint(2, 1), RoutingPoint(3, 1)), RoutingElement('metal1', None, RoutingPoint(3, 1), RoutingPoint(3, 0))]
    >>> net_name4="u_ibex_core/id_stage_i/decoder_i/n4"
    >>> routing_ports4=[]
    >>> routing_elements4=[RoutingElement('metal2', None, RoutingPoint(3, 2), RoutingPoint(3, 3)), RoutingElement('metal2', None, RoutingPoint(3, 3), RoutingPoint(2, 3))]
    >>> net_name5="u_ibex_core/id_stage_i/decoder_i/n5"
    >>> routing_ports5=[]
    >>> routing_elements5=[RoutingElement('metal3', 'via4', RoutingPoint(0, 1), RoutingPoint(1, 1)), RoutingElement('metal1', None, RoutingPoint(0, 1), RoutingPoint(0, 0))]
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
    (u_ibex_core/id_stage_i/decoder_i/n5: (0,1,1,1) -> (0,1,0,0), 'metal3')
    >>> net_name1="u_ibex_core/id_stage_i/decoder_i/n1"
    >>> routing_ports1=[]
    >>> routing_elements1=[RoutingElement('metal1', 'via1', RoutingPoint(100, 101), RoutingPoint(10, 101)), RoutingElement('metal2', None, RoutingPoint(100, 101), RoutingPoint(100, 50))]
    >>> net_name2="u_ibex_core/id_stage_i/decoder_i/n2"
    >>> routing_ports2=[]
    >>> routing_elements2=[RoutingElement('metal1', 'via2', RoutingPoint(56, 12), RoutingPoint(12, 12)), RoutingElement('metal1', None, RoutingPoint(12, 22), RoutingPoint(12, 12)), RoutingElement('metal1', None, RoutingPoint(12, 22), RoutingPoint(6, 22))]
    >>> net_name3="u_ibex_core/id_stage_i/decoder_i/n3"
    >>> routing_ports3=[]
    >>> routing_elements3=[RoutingElement('metal1', 'via3', RoutingPoint(2, 1), RoutingPoint(3, 1)), RoutingElement('metal1', None, RoutingPoint(3, 1), RoutingPoint(3, 0))]
    >>> net_name4="u_ibex_core/id_stage_i/decoder_i/n4"
    >>> routing_ports4=[]
    >>> routing_elements4=[RoutingElement('metal2', None, RoutingPoint(30, 200), RoutingPoint(30, 300)), RoutingElement('metal2', None, RoutingPoint(30, 300), RoutingPoint(30, 345)), RoutingElement('metal2', None, RoutingPoint(30, 300), RoutingPoint(100, 300))]
    >>> net_name5="u_ibex_core/id_stage_i/decoder_i/n5"
    >>> routing_ports5=[]
    >>> routing_elements5=[RoutingElement('metal3', 'via4', RoutingPoint(120, 111), RoutingPoint(110, 111)), RoutingElement('metal1', None, RoutingPoint(110, 111), RoutingPoint(110, 131))]
    >>> net1=Net(net_name1, routing_ports1, routing_elements1)
    >>> net2=Net(net_name2, routing_ports2, routing_elements2)
    >>> net3=Net(net_name3, routing_ports3, routing_elements3)
    >>> net4=Net(net_name4, routing_ports4, routing_elements4)
    >>> net5=Net(net_name5, routing_ports5, routing_elements5)
    >>> net_lst=[net1, net2, net3, net4, net5]
    >>> find_nearest_neighbour_for_net(net1, net_lst)
    (u_ibex_core/id_stage_i/decoder_i/n2: (56,12,12,12) -> (12,22,12,12) -> (12,22,6,22), 'metal1')
    >>> find_nearest_neighbour_for_net(net2, net_lst)
    (u_ibex_core/id_stage_i/decoder_i/n3: (2,1,3,1) -> (3,1,3,0), 'metal1')
    >>> find_nearest_neighbour_for_net(net3, net_lst)
    (u_ibex_core/id_stage_i/decoder_i/n2: (56,12,12,12) -> (12,22,12,12) -> (12,22,6,22), 'metal1')
    >>> find_nearest_neighbour_for_net(net4, net_lst)
    (u_ibex_core/id_stage_i/decoder_i/n4: (30,200,30,300) -> (30,300,30,345) -> (30,300,100,300), 'metal2')
    >>> find_nearest_neighbour_for_net(net5, net_lst)
    (u_ibex_core/id_stage_i/decoder_i/n5: (120,111,110,111) -> (110,111,110,131), 'metal3')
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

    print("Parsing def file...")
    net_list = parse(cli_arguments.def_file_name, cli_arguments.functional_unit)
    print("Done!")

    # filter unrouted nets
    net_list = list(filter(lambda net : len(net.routing_elements) > 0, net_list))


    if cli_arguments.grouping_mode == "accurate":
        distance_trees, layer_mapping = points_per_metal_layer(net_list)
    elif cli_arguments.grouping_mode == "insane":
        distance_trees, layer_mapping = points_per_metal_layer(net_list, interpolate=True)

    neighbouring_nets = list()
    for net in tqdm.tqdm(net_list,desc="Generating neigborhoods"):

        if cli_arguments.grouping_mode == "relaxed":
            closest_net, metal_layer = find_nearest_neighbour_for_net(net, net_list)
        elif cli_arguments.grouping_mode == "accurate":
            closest_net, metal_layer = find_minimum_distance_across_layers(net, distance_trees, layer_mapping)
        elif cli_arguments.grouping_mode == "insane":
            closest_net, metal_layer = find_minimum_distance_across_layers(net, distance_trees, layer_mapping, interpolate=True)

        pair = f"{net.net_name},{closest_net.net_name}"

        # For a combination 'a,b' checks whether 'b,a' exists already.
        if f"{closest_net.net_name},{net.net_name}" in neighbouring_nets:
            continue

        neighbouring_nets.append(f"{pair},{metal_layer}")

    # write to output file
    print(f"Exporting results to {cli_arguments.output_file}")
    with open(cli_arguments.output_file, "w") as output:
        for pair in neighbouring_nets:
            output.write(f"{pair}\n")

if __name__=="__main__":

    param_parser=argparse.ArgumentParser()

    param_parser.add_argument('-u', "--functional_unit", action = "store", help = "Specifies the targeted functional unit", required = True)
    param_parser.add_argument('-f', "--def_file_name", action = "store", help = "Input .def file", required = True, metavar = "xxx.def")
    param_parser.add_argument('-o', "--output_file", action = "store", help = "Output file 'xxx.map' ", default = "pair.map", metavar = "xxx_pair.map")
    param_parser.add_argument('-m', "--grouping_mode", action = "store", help = "Net grouping approach", default = "accurate", choices = ["accurate", "relaxed", "insane"])

    cli_arguments = param_parser.parse_args()

    main()


