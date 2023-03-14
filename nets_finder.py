import argparse 
import tqdm
import re 
import math 

from net_parsing import *
from copy import copy
from collections import defaultdict
from sklearn.neighbors import KDTree
from typing import List, Dict, Tuple, Any, Union
from matplotlib import pyplot as plt

import numpy as np


def plot_nets(nets: List[Net]) -> None:
    """
    This is case specific. Used for debug purposes. 
    This metal layer syntax is present in Nangate45nm 
    LEF file and is compliant with Nangate-based DEF 
    files ONLY.
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

        for routing_point in net.routing_points:

            if len(routing_point.points) == 2:
                plt.plot(
                    [routing_point.points[0].x, routing_point.points[1].x],
                    [routing_point.points[0].y, routing_point.points[1].y],
                    color = metal_layers[routing_point.metal_layer])
            else:
                plt.plot(routing_point.points[0].x, routing_point.points[0].y, color = metal_layers[routing_point.metal_layer])

    plt.show()

def walk_routing_element(element: RoutingPoint, step=10.0) -> List[Point]:
    """ 
    Walks the routing element from start to end and returns points on the element.
    Each point is in distance defined by the step parameter.
    >>> data = '''
    ... - net1
    ... ( PIN hart_id_i[31] ) ( u_ibex_core/U1 A2 )
    ... + ROUTED metal1 ( 0 1 ) ( * 100 )
    ...   NEW metal2 ( 0 1 ) via_2
    ...   NEW metal3 ( 0 1 ) ( 100 * )
    ... ;'''
    >>> f = parse_nets_section(data)
    >>> list(walk_routing_element(f[0].routing_points[0])) 
    [(0,1), (0,11), (0,21), (0,31), (0,41), (0,51), (0,61), (0,71), (0,81), (0,91), (0,100)]
    >>> list(walk_routing_element(f[0].routing_points[1]))
    [(0,1)]
    >>> list(walk_routing_element(f[0].routing_points[2]))
    [(0,1), (10,1), (20,1), (30,1), (40,1), (50,1), (60,1), (70,1), (80,1), (90,1), (100,1)]
    """
    start = element.points[0] 
    if len(element.points) == 1:
        yield element.points[0]
        return
    end = element.points[1]

    start = (start.x, start.y)
    end = (end.x, end.y)

    def _distance(start, end):
        return math.sqrt(math.pow(start[0] - end[0], 2.0) + math.pow(start[1] - end[1], 2.0))

    distance = _distance(start, end)
    difference = (end[0] - start[0], end[1] - start[1])
    direction = (difference[0] / max(0.001, distance), difference[1] / max(0.001, distance))

    yield element.points[0]
    current = start
    while True:
        current = (current[0] + step * direction[0], current[1] + step * direction[1])
        if _distance(start, current) >= distance:
            break
        yield Point(int(current[0]), int(current[1]))

    yield element.points[1]

def points_per_metal_layer(net_list: List[Net], interpolate: bool = False) -> Tuple[dict,dict]:

    metal_layer_mapping = defaultdict(list)

    for net in net_list:
        for element in net.routing_points:

            assert(len(element.points) <= 2), f"Element {element} has >2 points"
            points = list()
            for point in element.points:
                points += [point]
            else:
                # In interpolation mode we walk the whole metal strip
                # and add multiple points in equidistant locations.
                #points = walk_routing_element(element)
                pass 
            for point in points:
                metal_layer_mapping[element.metal_layer] \
                    .append((net, point.x, point.y))

    np_compliant_dict = dict()
    kdtrees_per_layer = dict()

    for metal_layer, net_points in tqdm.tqdm(metal_layer_mapping.items(),
            total=len(metal_layer_mapping.items()), 
            desc="Generating trees...", 
            ncols=80,
            colour="#00ff00",
            ascii="|#",
            unit=" trees"):

        np_compliant_dict[metal_layer] = np.empty((len(net_points),2))

        for index, (_, x, y) in enumerate(net_points):

            np_compliant_dict[metal_layer][index] = x, y

        kdtrees_per_layer[metal_layer] = KDTree(np_compliant_dict[metal_layer], metric="euclidean")

    return kdtrees_per_layer, metal_layer_mapping

def find_minimum_distance_for_starting_point(net: Net, nets: List[Net]) -> Tuple[Net, str]:
    """
    Computes the minimum distance of a given net based ONLY on the
    very first routing point ( x y ) for every net  
    >>> data = '''
    ... - net1
    ... ( PIN hart_id_i[31] ) ( u_ibex_core/U1 A2 )
    ... + ROUTED metal1 ( 0 1 ) ( 1 1 )
    ...   NEW metal2 ( 0 1 ) ( 0 0 )
    ... ;
    ... - net2
    ... ( PIN hart_id_i[30] ) ( u_ibex_core/U2 A3 )
    ... + ROUTED metal1 ( 2 2 ) ( 2 2 )
    ...   NEW metal2 ( 0 1 ) ( 0 0 )
    ... ;
    ... - net3 
    ... ( PIN hard_id_i[29] ) ( u_ibex_core/U3 A4 )
    ... + ROUTED metal1 ( 0 6 ) ( 3 1 )
    ...   NEW metal1 ( 5 5 ) ( 6 6 )
    ... ;'''
    >>> f = parse_nets_section(data)
    >>> find_minimum_distance_for_starting_point(f[0], f)
    (net2, 'metal1')
    >>> find_minimum_distance_for_starting_point(f[2], f)
    (net2, 'metal1')
    >>> find_minimum_distance_for_starting_point(f[1], f)
    (net1, 'metal1')
    """
    other_nets_in_same_layer = list()
    starting_metal_layer = net.routing_points[0].metal_layer

    for other in nets:
        
        if starting_metal_layer == other.routing_points[0].metal_layer \
        and nets.index(other) != nets.index(net):
            other_nets_in_same_layer.append(other)

    #No other nets exist in the same metal layer. Consider the same net twice.
    if len(other_nets_in_same_layer) == 0:
        return net, starting_metal_layer

    starting_point_distance_from_net = lambda other_net: math.dist(
        [net.routing_points[0].starting_point.x, \
        net.routing_points[0].starting_point.y], \
        [other_net.routing_points[0].starting_point.x, \
        other_net.routing_points[0].starting_point.y])

    nearest_node = min(other_nets_in_same_layer, key = starting_point_distance_from_net)

    assert nearest_node.routing_points[0].metal_layer == net.routing_points[0].metal_layer, "Nets on different metal layers!"
    return nearest_node, nearest_node.routing_points[0].metal_layer

def find_minimum_distance_across_layers(net: Net, KDtrees: Dict[str,KDTree], layer_mapping: dict, interpolate: bool = False) -> Tuple[Net,str]:
    """
    For every routing point of the given net, finds the neighboring net with the minimum distance.
    Out of these, it returns the one with the smallest distance to be its neighbour. Considers all
    layers. Optionally, interpolation mode can be used (computationally heavy) which breaks down 
    each metal strip in smaller segments and repeats the flow for each sub-strip. Better accuracy
    in the cost of computational time.
    """
    minimum_distance = np.inf
    minimum_distance_net_index = None
    minimum_distance_net_layer = None

    for routing_point in net.routing_points:
        tree = KDtrees[routing_point.metal_layer]

        if not interpolate:
            points = list()
            for point in routing_point.points:
                points += [point]
        else:
            # In interpolation mode we walk the whole metal strip
            # and add multiple points in equidistant locations. 
            points = walk_routing_element(routing_point)

        for point in points: 
            max_query_size = len(layer_mapping[routing_point.metal_layer])
            query_size = min(100, max_query_size)

            while query_size <= max_query_size:
                query_points = np.array([(point.x, point.y)])
                distances, indices = tree.query(query_points, k=query_size)
                for index, distance in zip(indices[0], distances[0]):
                    # Exclude the points of the net itself
                    if net.get_name() == layer_mapping[routing_point.metal_layer][index][0].get_name():
                        continue

                    if distance < minimum_distance:
                        minimum_distance = distance
                        minimum_distance_net_index = index
                        minimum_distance_net_layer = routing_point.metal_layer

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

def main():
    
    ####################################
    # Isolate NETS region of .def file #
    ####################################
    try:
        with open(cli_arguments.def_file_name, "r") as input_file:
            data = input_file.read()
    except OSError:
        exit(f"Unable to open file \"{cli_arguments.def_file_name}\" for reading.")

    match = re.search(r'\bNETS\b\s+\d+\s*;(.*)\bEND NETS\b', data, re.DOTALL | re.MULTILINE)

    if not match:
        raise ValueError("Invalid input file")

    data = match.group(1)

    ####################################
    # Callback to Lark-based parser    #
    ####################################
    print(f"Parsing {cli_arguments.def_file_name}...")
    nets = parse_nets_section(data)

    # filter out redundant nets 
    stress_target_nets = [ net for net in nets if cli_arguments.functional_unit in net.get_name() and net.routing_points != None ]

    assert (len(stress_target_nets) > 0), f"Unable to extract nets of unit {cli_arguments.functional_unit}"

    if cli_arguments.grouping_mode == "accurate":
        distance_trees, layer_mapping = points_per_metal_layer(stress_target_nets)
    elif cli_arguments.grouping_mode == "insane":
        distance_trees, layer_mapping = points_per_metal_layer(stress_target_nets, interpolate=True)

    neighbouring_nets = list()
    for net in tqdm.tqdm(stress_target_nets, 
            total=len(stress_target_nets), 
            desc="Generating pairs...", 
            ncols=80,
            colour="#00ff00",
            ascii="|#",
            unit=" nets"):
        if cli_arguments.grouping_mode == "relaxed":
            closest_net, metal_layer = find_minimum_distance_for_starting_point(net, stress_target_nets)
        elif cli_arguments.grouping_mode == "accurate":
            closest_net, metal_layer = find_minimum_distance_across_layers(net, distance_trees, layer_mapping)
        elif cli_arguments.grouping_mode == "insane":
            closest_net, metal_layer = find_minimum_distance_across_layers(net, distance_trees, layer_mapping, interpolate=True)
        pair = f"{net.get_name()},{closest_net.get_name()}"

        # For a combination 'a,b' checks whether 'b,a' exists already.
        if f"{closest_net.get_name()},{net.get_name()}" in neighbouring_nets:
            continue
        neighbouring_nets.append(f"{pair},{metal_layer}")

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
