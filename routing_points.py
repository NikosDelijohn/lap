from lark import Lark, Transformer, v_args, Token, Tree, logger 
from dataclasses import dataclass
from typing import Union, List, Tuple, Any
from collections import namedtuple

import logging
logger.setLevel(logging.WARN)

ROUTING_POINTS_GRAMMAR = r"""
                                                        //                              
    net_statement: "-" header shield_nets virtual_pins  xtalk? non_default_rule? regular_wirings? use? net_properties ";" \
         source? fixed_bump? // frequency? estimated_capacitance? weight? net_properties ";"

    header: NET_NAME ( "(" component_and_pin ")" )*
        ?component_and_pin: COMP_NAME PIN_NAME synthesized?
        ?synthesized: "+ SYNTHESIZED"
    ?shield_nets: ("+ SHIELDNET" NET_NAME)*
    virtual_pins: virtual_pin* 
        ?virtual_pin: "+ VPIN" VPIN_NAME ("LAYER" LAYER_NAME)? vpoint vpoint vpin_placement*
        !vpin_placement: "PLACED" vpoint ORIENTATION
                       | "FIXED" vpoint ORIENTATION 
                       | "COVER" vpoint ORIENTATION 
    ?xtalk: "+ XTALK" XTALK_VALUE
    ?non_default_rule: "+ NONDEFAULTRULE" RULE_NAME
    ?source: "+ SOURCE" SOURCE_KEYWORD
    ?fixed_bump: "+ FIXEDBUMP" 
    ?frequency: "+ FREQUENCY" FREQUENCY_IN_HERTZ
    ?original_net: "+ ORIGINAL" NET_NAME
    ?use: "+ USE" USE_KEYWORD
    ?pattern: "+ PATTERN" PATTERN_KEYWORD
    ?estimated_capacitance: "+ ESTCAP" FLOAT
    ?weight: "+ WEIGHT" POS_INT
    net_properties: ("+ PROPERTY" net_property+ )*
        ?net_property: PROPERTY_NAME PROPERTY_VALUE // NOTE: Property Name shall not contain +. Otherwise it is parsed as net_property ( + := PROPRETY issue )

    regular_wirings: regular_wiring* 
    regular_wiring: "+" WIRING LAYER_NAME taper? style? routing_point new_statement+
    new_statement: "NEW" layer_name taper? style? routing_point

    ?wiring_keyword: WIRING
    ?layer_name: LAYER_NAME 
    ?taper: "TAPER" | "TAPERRULE" RULE_NAME
    ?style: "STYLE" POS_INT
    
    routing_point: point trailing_option+
    trailing_option: mask_point | mask_via | mask_rect | virtual_connection 
    
    mask_point: mask? point
    mask_via: mask? via_name orientation?
    mask_rect: mask? "RECT" "(" COORDINATE COORDINATE COORDINATE COORDINATE ")"
    virtual_connection: "VIRTUAL" point
   
    ?point: "(" COORDINATE COORDINATE POS_INT? ")" 
    ?vpoint: "(" COORDINATE COORDINATE ")"
    ?via_name: VIA_NAME 
    ?orientation: ORIENTATION
    ?mask: "MASK" MASK_NUMBER

    NET_NAME: /[^\s\+]+/
    PIN_NAME: /[^\s\+]+/
    VPIN_NAME: /[^\s\+]+/
    COMP_NAME: /[^\s\+]+/
    COORDINATE: /-?\d+/ | "*"
    VIA_NAME: /[^\s\+]+/
    PROPERTY_NAME: /[^\s\+]+/ 
    PROPERTY_VALUE: FLOAT | POS_INT | /[^\s\+]+/
    MASK_NUMBER: /\d+/
    LAYER_NAME: /[^\s\+]+/
    RULE_NAME: /[^\s\+]+/
    XTALK_VALUE: /\d{1,3}/
    USE_KEYWORD: "ANALOG" | "CLOCK" | "GROUND" | "POWER" | "RESET" | "SCAN" | "SIGNAL" | "TIEOFF"
    SOURCE_KEYWORD: "DIST" | "NETLIST" | "TEST" | "TIMING" | "USER"
    PATTERN_KEYWORD: "BALANCED" | "STEINER" | "TRUNK" | "WIREDLOGIC"
    ORIENTATION: "N" | "S" | "W" | "E" | "FN" | "FS" | "FW" | "FE"
    WIRING: "COVER" | "FIXED" | "ROUTED" | "NOSHIELD"
    FREQUENCY_IN_HERTZ: FLOAT

    %import common.INT -> POS_INT
    %import common.FLOAT 
    %import common.WS
    %ignore WS
"""
Property = namedtuple('Property', ['name', 'value'])

@dataclass 
class ComponentAndPort:
    component_name: str 
    port_name: str 
    synthesized: str = None

    def __repr__(self):
        return f"PIN {self.port_name}" if self.component_name == "PIN" \
          else f"{self.component_name}/{self.port_name}"
     
    def is_synthesized(self):
        return self.synthesized != None 

@dataclass
class NetHeader:
    net_name: str
    connecting_components: List[ComponentAndPort]

    def __repr__(self):
        return f"{self.net_name}: {' -- '.join([str(x) for x in self.connecting_components])}"

@dataclass 
class Point: 
    x: Union[int,str]
    y: Union[int,str]
    ext: int = None 
    mask: str = None 
    virtual: bool = None

    def __repr__(self) -> str:
        return f"({self.x},{self.y})"
    
    def set_mask(self, mask: str) -> None:
        self.mask = mask

    def set_virtual(self, value: bool) -> None:
        self.virtual = value

    def set_x(self, x: int) -> None: 
        self.x = x 

    def set_y(self, y: int) -> None:
        self.y = y

@dataclass
class VirtualPin:
    pin_name: str 
    first_point: Point 
    second_point: Point 
    metal_layer: str = None
    placement: Union[Tuple[str,Point],Tuple[str,Point,str]] = None
    
    def __repr__(self):
        return f"VPIN: {self.pin_name} ({self.first_point},{self.second_point})"

    def get_metal_layer(self) -> str:
        return self.metal_layer
    
    def get_placement(self) -> Union[Tuple[str,Point],Tuple[str,Point,str]]:
        return self.placement

@dataclass 
class Via:
    name: str 
    mask: str = None 
    orient: str = None 

    def __repr__(self) -> str: 
        return f"{self.name}"

@dataclass 
class Rect:
    x1: int 
    y1: int 
    x2: int 
    y2: int 
    mask: str = None 

    def __repr__(self) -> str:
        return f"[({self.x1},{self.y1}),({self.x2},{self.y2})]"

@dataclass
class RoutingPoint:
    starting_point: Point  
    trailing_modules: List[Union[Point, Via, Rect]]
    metal_layer: str = None
    
    def __repr__(self) -> str:
        return f"({self.starting_point.x},{self.starting_point.y}) -> {' -> '.join([str(x) for x in self.trailing_modules if isinstance(x,Point)])}"
    
    def normalize(self) -> None:
        
        prev_x = self.starting_point.x 
        prev_y = self.starting_point.y 

        for elem in self.trailing_modules:

            if isinstance(elem, Point):

                if elem.x == '*': 
                    elem.set_x(prev_x)
                if elem.y == '*':
                    elem.set_y(prev_y)

                prev_x = elem.x 
                prev_y = elem.y 

    def set_metal_layer(self, metal_layer: str) -> None:
        self.metal_layer = metal_layer

@dataclass 
class NetWiring: 
    routing_points: List[RoutingPoint]   

    def __repr__(self) -> str: 
        return f"{' --> '.join([str(x) for x in self.routing_points])}"
    
    def normalize(self) -> None:
        for routing_point in self.routing_points:
            routing_point.normalize()
    
class RoutingPointsTransformer(Transformer):

    def get_token(self, tree: Tree, rule: str) -> Token: 
        return list(filter(lambda x: isinstance(x, Token) and x.type == rule, tree.children))

    @v_args(inline=True)
    def point(self, x: str, y: str, ext: str = None, mask: str = None) -> Point:
        """
        >>> data = ''' ( 0 -1 ) ''' 
        >>> Lark(ROUTING_POINTS_GRAMMAR, parser='lalr', start='point', transformer=RoutingPointsTransformer()).parse(data)
        (0,-1)
        >>> data = ''' ( 0 -31 3 ) ''' 
        >>> Lark(ROUTING_POINTS_GRAMMAR, parser='lalr', start='point', transformer=RoutingPointsTransformer()).parse(data)
        (0,-31)
        """
        return Point(
            int(x) if x != '*' else str(x),
            int(y) if y != '*' else str(y),
            int(ext) if ext else None,
            str(mask) if mask else None)
    
    @v_args(inline=True)
    def mask_point(self, *args) -> Point:
        """
        >>> data = ''' MASK 24 ( * 24500 ) ''' 
        >>> point = Lark(ROUTING_POINTS_GRAMMAR, parser='lalr', start='mask_point', transformer=RoutingPointsTransformer()).parse(data)
        >>> point
        (*,24500)
        >>> point.mask
        '24'
        >>> print(point.ext)
        None
        >>> data = ''' MASK 24 ( * 24500 45 ) ''' 
        >>> point = Lark(ROUTING_POINTS_GRAMMAR, parser='lalr', start='mask_point', transformer=RoutingPointsTransformer()).parse(data)
        >>> point.ext
        45
        """
        if len(args) == 2: # [MASK maskNum] present
            point = args[1]
            point.set_mask(str(args[0]))
            return point 
        
        return args[0]
    
    @v_args(tree=True)
    def mask_via(self, tree) -> Via:
        """
        >>> data = '''MASK 012 via1_4 N'''
        >>> via = Lark(ROUTING_POINTS_GRAMMAR, parser='lalr', start='mask_via', transformer=RoutingPointsTransformer()).parse(data)
        >>> via 
        via1_4
        >>> via.orient
        'N'
        >>> data = ''' via2_3 '''
        >>> via = Lark(ROUTING_POINTS_GRAMMAR, parser='lalr', start='mask_via', transformer=RoutingPointsTransformer()).parse(data)
        >>> via
        via2_3
        >>> print(via.mask)
        None
        >>> print(via.orient)
        None
        """
        mask = self.get_token(tree, rule="MASK_NUMBER")
        orient = self.get_token(tree, rule="ORIENTATION")
        
        return Via(
            self.get_token(tree, rule="VIA_NAME")[0].value,
            mask[0].value if mask else None, 
            orient[0].value if orient else None)
    
    @v_args(inline=True)
    def mask_rect(self, *args) -> Rect:
        """
        >>> data = '''MASK 3 RECT ( 1 2 3 4 )'''
        >>> rect = Lark(ROUTING_POINTS_GRAMMAR, parser='lalr', start='mask_rect', transformer=RoutingPointsTransformer()).parse(data)
        >>> rect 
        [(1,2),(3,4)]
        >>> rect.mask
        '3'
        >>> data = '''RECT ( 5 6 7 8 )'''
        >>> rect = Lark(ROUTING_POINTS_GRAMMAR, parser='lalr', start='mask_rect', transformer=RoutingPointsTransformer()).parse(data)
        >>> rect 
        [(5,6),(7,8)]
        >>> print(rect.mask)
        None
        """
        if len(args) == 5: # [MASK maskNum] present
            points = list(map(int,args[1:]))
            mask = str(args[0])
            return Rect(*points, mask)
   
        points = list(map(int,args))
        return Rect(*points)

    @v_args(inline=True)
    def virtual_connection(self, point: Point) -> Point:
        """
        >>> data = ''' VIRTUAL ( 0 -1 ) ''' 
        >>> point = Lark(ROUTING_POINTS_GRAMMAR, parser='lalr', start='virtual_connection', transformer=RoutingPointsTransformer()).parse(data)
        >>> point 
        (0,-1)
        >>> point.virtual
        True
        """
        point.set_virtual(True)
        return point    
    
    @v_args(inline=True)
    def trailing_option(self, option: Union[Point,Via,Rect]) -> Union[Point,Via,Rect]:
        """
        >>> data = '''( * 24500 )'''
        >>> rect = Lark(ROUTING_POINTS_GRAMMAR, parser='lalr', start='trailing_option', transformer=RoutingPointsTransformer()).parse(data)
        >>> rect 
        (*,24500)
        >>> print(rect.mask)
        None
        >>> data = ''' VIRTUAL ( 1 2 )'''
        >>> virt = Lark(ROUTING_POINTS_GRAMMAR, parser='lalr', start='trailing_option', transformer=RoutingPointsTransformer()).parse(data)
        >>> virt
        (1,2)
        >>> virt.virtual
        True
        >>> data = ''' MASK 24 ( 4 3 ) ''' 
        >>> point = Lark(ROUTING_POINTS_GRAMMAR, parser='lalr', start='trailing_option', transformer=RoutingPointsTransformer()).parse(data)
        >>> point
        (4,3)
        >>> point.mask
        '24'
        """
        return option
    
    @v_args(inline=True)
    def routing_point(self, starting_point, *others) -> RoutingPoint:
        """
        >>> data = ''' ( 282150 22260 ) ( 288990 * ) MASK 23 ( * 22262 ) via2_5 '''
        >>> point = Lark(ROUTING_POINTS_GRAMMAR, parser='lalr', start='routing_point', transformer=RoutingPointsTransformer()).parse(data)
        >>> point 
        (282150,22260) -> (288990,*) -> (*,22262)
        >>> point.normalize()
        >>> point
        (282150,22260) -> (288990,22260) -> (288990,22262)
        >>> data = ''' ( 10 10 ) ( 20 * ) MASK 1 ( 20 20 ) MASK 031 VIA1_2 '''
        >>> point = Lark(ROUTING_POINTS_GRAMMAR, parser='lalr', start='routing_point', transformer=RoutingPointsTransformer()).parse(data)
        >>> point
        (10,10) -> (20,*) -> (20,20)
        """
        return RoutingPoint(starting_point, [x for x in others], metal_layer=None)

    @v_args(inline=True)
    def new_statement(self, *args) -> RoutingPoint:
        """
        >>> data = ''' NEW metal2 TAPER STYLE 20 ( 275690 21980 ) ( * 22260 ) via2_5 ( 27000 * )'''
        >>> rp = Lark(ROUTING_POINTS_GRAMMAR, parser='lalr', start='new_statement', transformer=RoutingPointsTransformer()).parse(data)
        >>> rp
        (275690,21980) -> (*,22260) -> (27000,*)
        >>> rp.normalize()
        >>> rp
        (275690,21980) -> (275690,22260) -> (27000,22260)
        >>> rp.metal_layer
        'metal2'
        """
        # REMARK: Ignoring TAPER and STYLE for now  
        layer_name = str(args[0])
        routing_point = args[-1]
        routing_point.set_metal_layer(layer_name)
        return routing_point
    
    @v_args(tree=True)
    def regular_wiring(self, tree) -> NetWiring:
        """
        >>> data = '''+ ROUTED metal2 ( 283290 22260 ) ( * 22820 ) via2_8
        ... NEW metal3 ( 282910 22820 ) ( * 23380 )
        ... NEW metal3 ( 278730 23380 ) ( * 23660 )
        ... NEW metal3 ( 267710 23380 ) ( * 23660 )
        ... NEW metal2 ( 266950 23660 ) ( * 24500 ) via1_4 '''
        >>> wiring = Lark(ROUTING_POINTS_GRAMMAR, parser='lalr', start='regular_wiring', transformer=RoutingPointsTransformer()).parse(data) 
        >>> wiring # doctest: +NORMALIZE_WHITESPACE
        (283290,22260) -> (*,22820) --> 
        (282910,22820) -> (*,23380) --> 
        (278730,23380) -> (*,23660) --> 
        (267710,23380) -> (*,23660) --> 
        (266950,23660) -> (*,24500)
        >>> wiring.normalize()
        >>> wiring # doctest: +NORMALIZE_WHITESPACE
        (283290,22260) -> (283290,22820) --> 
        (282910,22820) -> (282910,23380) --> 
        (278730,23380) -> (278730,23660) --> 
        (267710,23380) -> (267710,23660) --> 
        (266950,23660) -> (266950,24500)
        >>> [x.metal_layer for x in wiring.routing_points]
        ['metal2', 'metal3', 'metal3', 'metal3', 'metal2']
        """
        initial_metal_layer = self.get_token(tree, "LAYER_NAME")[0].value
        routing_points = list(filter(lambda x: isinstance(x,RoutingPoint), tree.children))
        routing_points[0].set_metal_layer(initial_metal_layer)

        return NetWiring(routing_points)

    @v_args(inline=True)
    def component_and_pin(self, component_name: str, pin_name: str, synthesized: str = None) -> ComponentAndPort:
        """
        >>> data = ''' top_core/submodule_a/submodule_b INPUT1 '''
        >>> Lark(ROUTING_POINTS_GRAMMAR, parser='lalr', start='component_and_pin', transformer=RoutingPointsTransformer()).parse(data) 
        top_core/submodule_a/submodule_b/INPUT1
        >>> Lark(ROUTING_POINTS_GRAMMAR, parser='lalr', start='component_and_pin', transformer=RoutingPointsTransformer()).parse(data).is_synthesized()
        False
        >>> data = ''' top_core/submodule_a/submodule_b INPUT1 + SYNTHESIZED '''
        >>> Lark(ROUTING_POINTS_GRAMMAR, parser='lalr', start='component_and_pin', transformer=RoutingPointsTransformer()).parse(data) 
        top_core/submodule_a/submodule_b/INPUT1
        >>> Lark(ROUTING_POINTS_GRAMMAR, parser='lalr', start='component_and_pin', transformer=RoutingPointsTransformer()).parse(data).is_synthesized()
        True
        >>> data = ''' PIN pepegius_megistus + SYNTHESIZED '''
        >>> Lark(ROUTING_POINTS_GRAMMAR, parser='lalr', start='component_and_pin', transformer=RoutingPointsTransformer()).parse(data)
        PIN pepegius_megistus
        >>> Lark(ROUTING_POINTS_GRAMMAR, parser='lalr', start='component_and_pin', transformer=RoutingPointsTransformer()).parse(data).is_synthesized()
        True
        """
        return ComponentAndPort(component_name, pin_name, synthesized)

    @v_args(inline=True)
    def header(self, pin_name_or_join: str, *args):
        """
        >>> data = ''' top_core/submodule_a/net3
        ... ( top_core/submodule_a/register_\[3\] CK )
        ... ( top_core/submodule_a/register_\[2\] CK )
        ... ( PIN IN1 ) '''
        >>> Lark(ROUTING_POINTS_GRAMMAR, parser='lalr', start='header', transformer=RoutingPointsTransformer()).parse(data)
        top_core/submodule_a/net3: top_core/submodule_a/register_\[3\]/CK -- top_core/submodule_a/register_\[2\]/CK -- PIN IN1
        >>> data = ''' MUSTJOIN ( top_core/submodule_w PIN5 ) '''
        >>> Lark(ROUTING_POINTS_GRAMMAR, parser='lalr', start='header', transformer=RoutingPointsTransformer()).parse(data)
        MUSTJOIN: top_core/submodule_w/PIN5
        """
        return NetHeader(pin_name_or_join, [x for x in args])    

    @v_args(tree=True) 
    def virtual_pin(self, tree):
        """
        >>> data = '''+ VPIN M7K.v2 LAYER M2 ( -10 -10 ) ( 10 10 ) FIXED ( 10 10 ) FS'''
        >>> test = Lark(ROUTING_POINTS_GRAMMAR, parser='lalr', start='virtual_pin', transformer=RoutingPointsTransformer()).parse(data) 
        >>> test
        VPIN: M7K.v2 ((-10,-10),(10,10))
        >>> test.get_metal_layer()
        'M2'
        >>> test.get_placement()
        ('FIXED', (10,10), 'FS')
        >>> data = '''+ VPIN M7K.v2 LAYER M2 ( -10 -10 ) ( 10 10 ) FIXED ( 10 10 ) S'''
        >>> test = Lark(ROUTING_POINTS_GRAMMAR, parser='lalr', start='virtual_pin', transformer=RoutingPointsTransformer()).parse(data) 
        >>> test
        VPIN: M7K.v2 ((-10,-10),(10,10))
        >>> data = '''+ VPIN M7K.v2 ( -10 -10 ) ( 10 10 ) '''
        >>> Lark(ROUTING_POINTS_GRAMMAR, parser='lalr', start='virtual_pin', transformer=RoutingPointsTransformer()).parse(data) 
        VPIN: M7K.v2 ((-10,-10),(10,10))
        """
        tokens = tree.children 
        
        layer_token = self.get_token(tree,"LAYER_NAME")
        placement_ast = list(filter(lambda x: isinstance(x, Tree), tokens))

        name = tokens[0].value 
        metal_layer = layer_token[0].value if layer_token else None 
        x = tokens[2] if layer_token else tokens[1]
        y = tokens[3] if layer_token else tokens[2] 

        if placement_ast:

            placement_tokens = placement_ast[0].children    
            placement = (str(placement_tokens[0]), placement_tokens[1], str(placement_tokens[2]))
            
        return VirtualPin(name, x, y, metal_layer, placement if placement_ast else None)

    @v_args(inline=True)
    def vpoint(self, x: str, y: str) -> Point:
        return Point(int(x),int(y))

    def virtual_pins(self, list_of_virtual_pins):
        """
        >>> data = '''+ VPIN M7K.v2 LAYER M2 ( -10 -10 ) ( 10 10 ) FIXED ( 10 10 ) FS
        ... + VPIN M7K.v3 LAYER M2 ( -13 12 ) ( 50 70 ) FIXED ( 10 10 ) N
        ... + VPIN M7K.v2 LAYER M2 ( -134 -10 ) ( 10 14 )'''
        >>> Lark(ROUTING_POINTS_GRAMMAR, parser='lalr', start='virtual_pins', transformer=RoutingPointsTransformer()).parse(data) 
        [VPIN: M7K.v2 ((-10,-10),(10,10)), VPIN: M7K.v3 ((-13,12),(50,70)), VPIN: M7K.v2 ((-134,-10),(10,14))]
        """
        return list_of_virtual_pins
    
    shield_nets = lambda self, vals : list(map(str,vals))
    non_default_rule = lambda self, rule_name : str(rule_name)
    estimated_capacitance = lambda self, value : float(value)
    original_net = lambda self, net_name : str(net_name)
    weight = lambda self, value : int(value) 
    pattern = lambda self, pattern_type : str(pattern_type)
    use = lambda self, use_type : str(use_type)
    source = lambda self, source_type : str(source_type)
    fixed_bump = lambda self, _ : True
    xtalk = lambda self, value : int(value)
    frequency = lambda self, value : float(value)
    regular_wirings = lambda self, list_of_wiring_statements: list_of_wiring_statements
    net_property = lambda self, name, value : Property(name,value)
    net_properties = lambda self, list_of_properties: list_of_properties

    @v_args(inline=True)
    def net_statement(self, 
        header: NetHeader, 
        shield_nets: List[str] = None,
        virtual_pins: List[VirtualPin] = None,
        xtalk: int = None,
        non_default_rule: str = None,
        regular_wirings: List[NetWiring] = None,
        source: str = None, 
        fixed_bump: bool = None,
        frequency: float = None,
        original_net: str = None,
        use: str = None, 
        pattern: str = None, 
        estimated_capacitance: str = None,
        weight: int = None, 
        properties: List[Property] = None) :
        """
        >>> data = '''- u_ibex_core/ex_block_i/gen_multdiv_fast_multdiv_i/n2491
        ... ( u_ibex_core/ex_block_i/gen_multdiv_fast_multdiv_i/U2374 A )
        ... ( u_ibex_core/ex_block_i/gen_multdiv_fast_multdiv_i/U2348 CO )
        ... + VPIN M7K.v2 LAYER M2 ( -10 -10 ) ( 10 10 ) FIXED ( 10 10 ) FS
        ... + VPIN M7K.v3 LAYER M2 ( -13 12 ) ( 50 70 ) FIXED ( 10 10 ) N
        ... + VPIN M7K.v2 LAYER M2 ( -134 -10 ) ( 10 14 )
        ... + XTALK 200 
        ... + ROUTED metal3 ( 252170 114660 ) ( 252510 * ) via2_5
        ... NEW metal4 ( 252170 113820 ) ( * 114660 ) via3_2
        ... NEW metal5 ( 249370 113820 ) ( 252170 * ) via4_0
        ... NEW metal6 ( 249370 102620 ) ( * 113820 ) via5_0 
        ... + PROPERTY property1 15.40 ;'''
        >>> Lark(ROUTING_POINTS_GRAMMAR, parser='lalr', start='net_statement', transformer=RoutingPointsTransformer()).parse(data) 
        """
        print(header)
        print(shield_nets)
        print(virtual_pins)
        print(xtalk)
        print(non_default_rule)
        print(regular_wirings)
        print(properties)
        

if __name__ == "__main__":
    data = '''- u_ibex_core/ex_block_i/gen_multdiv_fast_multdiv_i/n2491
    ( u_ibex_core/ex_block_i/gen_multdiv_fast_multdiv_i/U2374 A )
    ( u_ibex_core/ex_block_i/gen_multdiv_fast_multdiv_i/U2348 CO )
    + VPIN TEST LAYER M2 ( 123 123 ) ( 123 123 ) PLACED ( 10 10 ) N
    + ROUTED metal3 ( 252170 114660 ) ( 252510 * ) via2_5
      NEW metal4 ( 252170 113820 ) ( * 114660 ) via3_2
      NEW metal5 ( 249370 113820 ) ( 252170 * ) via4_0
      NEW metal6 ( 249370 102620 ) ( * 113820 ) via5_0
      NEW metal6 ( 249370 51660 ) ( * 98140 )
      NEW metal5 ( 247690 51660 ) ( 249370 * ) via5_0
      NEW metal3 ( 245670 51660 ) ( 247690 * ) via3_2
      NEW metal2 ( 245670 50260 ) ( * 51660 ) via2_5
      NEW metal2 ( 241490 121660 ) ( * 122500 ) via1_4 
    + USE POWER ; '''
    #
    parser = Lark(ROUTING_POINTS_GRAMMAR, 
        parser='lalr',
        start='net_statement', 
        transformer=RoutingPointsTransformer())
    parser.parse(data)