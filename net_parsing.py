from lark import Lark, Transformer, v_args, Token, Tree
from dataclasses import dataclass
from typing import Union, List, Tuple, Any
from collections import namedtuple

NET_GRAMMAR = \
r"""
    net_statements: net_statement*       
    net_statement: "-" header                 \
                       shield_nets            \
                       virtual_pins           \
                       xtalk?                 \
                       non_default_rule?      \
                       regular_wirings        \
                       source?                \
                       fixed_bump?            \
                       frequency?             \
                       original_net?          \
                       use?                   \
                       pattern?               \
                       estimated_capacitance? \
                       weight?                \
                       net_properties        ";"

    header: NET_NAME ( "(" component_and_pin ")" )*
    ?component_and_pin: COMP_NAME PIN_NAME synthesized?
    ?synthesized: "+ SYNTHESIZED"

    ?shield_nets: ("+ SHIELDNET" NET_NAME)*
   
    virtual_pins: virtual_pin* 
    ?virtual_pin: "+ VPIN" VPIN_NAME ("LAYER" LAYER_NAME)? vpoint vpoint vpin_placement*
    ?vpoint: "(" COORDINATE COORDINATE ")"
    !vpin_placement: "PLACED" vpoint ORIENTATION
                   | "FIXED" vpoint ORIENTATION 
                   | "COVER" vpoint ORIENTATION 

    xtalk: "+ XTALK" XTALK_VALUE
    
    non_default_rule: "+ NONDEFAULTRULE" RULE_NAME
    
    source: "+ SOURCE" SOURCE_KEYWORD
    
    fixed_bump: "+ FIXEDBUMP" 
   
    frequency: "+ FREQUENCY" FREQUENCY_IN_HERTZ
    
    original_net: "+ ORIGINAL" NET_NAME
    
    use: "+ USE" USE_KEYWORD
    
    pattern: "+ PATTERN" PATTERN_KEYWORD
   
    estimated_capacitance: "+ ESTCAP" FLOAT
   
    weight: "+ WEIGHT" POS_INT
    
    net_properties:  net_property*
    ?net_property: "+ PROPERTY" PROPERTY_NAME PROPERTY_VALUE // NOTE: Property Name shall not contain +. Otherwise it is parsed as net_property ( + := PROPRETY issue )

    regular_wirings: regular_wiring* 
    regular_wiring: "+" WIRING LAYER_NAME taper? style? routing_point new_statement*
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
    ?via_name: VIA_NAME 
    ?orientation: ORIENTATION
    ?mask: "MASK" MASK_NUMBER
    
    ///////////////
    // TERMINALS // 
    ///////////////

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
    points: List[Point] = None
    
    def __repr__(self) -> str:
        return f"({self.starting_point.x},{self.starting_point.y}) -> {' -> '.join([str(x) for x in self.trailing_modules if isinstance(x,(Point,Via))])}"
    
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

    def _set_point_list(self) -> List[Point]:

        self.points = [self.starting_point]
        for module in self.trailing_modules:
            if isinstance(module,Point):
                self.points.append(module)

@dataclass 
class NetWiring: 
    routing_points: List[RoutingPoint]   

    def __repr__(self) -> str: 
        return f"{' --> '.join([str(x) for x in self.routing_points])}"
    
    def normalize(self) -> None:
        for routing_point in self.routing_points:
            routing_point.normalize()

@dataclass 
class Net:
    header: NetHeader
    shield_nets: List[str] = None
    virtual_pins: List[VirtualPin] = None
    xtalk: int = None
    non_default_rule: str = None
    regular_wirings: List[NetWiring] = None
    source: str = None 
    fixed_bump: bool = None
    frequency: float = None
    original_net: str = None
    use: str = None 
    pattern: str = None 
    estimated_capacitance: float = None
    weight: int = None
    properties: List[Property] = None
    routing_points: List[RoutingPoint] = None
    

    def __repr__(self) -> str:
        return f"{self.header.net_name}"

    def get_name(self) -> str:
        return self.header.net_name
    
    def normalize(self) -> None:
        if self.regular_wirings:
            for wire in self.regular_wirings: 
                wire.normalize()

    def _set_routing_points(self) -> None:
        tmp = list()
        if self.regular_wirings:
            for wiring_statement in self.regular_wirings:
                for routing_point in wiring_statement.routing_points:
                    tmp.append(routing_point)
        self.routing_points = tmp 
    
    def _set_point_list(self) -> None:
        
        if self.regular_wirings:
            for net_wiring in self.regular_wirings:
                for routing_point in net_wiring.routing_points:
                    routing_point._set_point_list()

class NetTransformer(Transformer):

    def get_token(self, tree: Tree, rule: str) -> Token: 
        return list(filter(lambda x: isinstance(x, Token) and x.type == rule, tree.children))

    @v_args(inline=True)
    def point(self, x: str, y: str, ext: str = None, mask: str = None) -> Point:
        """
        >>> data = ''' ( 0 -1 ) ''' 
        >>> Lark(NET_GRAMMAR, parser='lalr', start='point', transformer=NetTransformer()).parse(data)
        (0,-1)
        >>> data = ''' ( 0 -31 3 ) ''' 
        >>> Lark(NET_GRAMMAR, parser='lalr', start='point', transformer=NetTransformer()).parse(data)
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
        >>> point = Lark(NET_GRAMMAR, parser='lalr', start='mask_point', transformer=NetTransformer()).parse(data)
        >>> point
        (*,24500)
        >>> point.mask
        '24'
        >>> print(point.ext)
        None
        >>> data = ''' MASK 24 ( * 24500 45 ) ''' 
        >>> point = Lark(NET_GRAMMAR, parser='lalr', start='mask_point', transformer=NetTransformer()).parse(data)
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
        >>> via = Lark(NET_GRAMMAR, parser='lalr', start='mask_via', transformer=NetTransformer()).parse(data)
        >>> via 
        via1_4
        >>> via.orient
        'N'
        >>> data = ''' via2_3 '''
        >>> via = Lark(NET_GRAMMAR, parser='lalr', start='mask_via', transformer=NetTransformer()).parse(data)
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
        >>> rect = Lark(NET_GRAMMAR, parser='lalr', start='mask_rect', transformer=NetTransformer()).parse(data)
        >>> rect 
        [(1,2),(3,4)]
        >>> rect.mask
        '3'
        >>> data = '''RECT ( 5 6 7 8 )'''
        >>> rect = Lark(NET_GRAMMAR, parser='lalr', start='mask_rect', transformer=NetTransformer()).parse(data)
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
        >>> point = Lark(NET_GRAMMAR, parser='lalr', start='virtual_connection', transformer=NetTransformer()).parse(data)
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
        >>> rect = Lark(NET_GRAMMAR, parser='lalr', start='trailing_option', transformer=NetTransformer()).parse(data)
        >>> rect 
        (*,24500)
        >>> print(rect.mask)
        None
        >>> data = ''' VIRTUAL ( 1 2 )'''
        >>> virt = Lark(NET_GRAMMAR, parser='lalr', start='trailing_option', transformer=NetTransformer()).parse(data)
        >>> virt
        (1,2)
        >>> virt.virtual
        True
        >>> data = ''' MASK 24 ( 4 3 ) ''' 
        >>> point = Lark(NET_GRAMMAR, parser='lalr', start='trailing_option', transformer=NetTransformer()).parse(data)
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
        >>> point = Lark(NET_GRAMMAR, parser='lalr', start='routing_point', transformer=NetTransformer()).parse(data)
        >>> point 
        (282150,22260) -> (288990,*) -> (*,22262) -> via2_5
        >>> point.normalize()
        >>> point
        (282150,22260) -> (288990,22260) -> (288990,22262) -> via2_5
        >>> data = ''' ( 10 10 ) ( 20 * ) MASK 1 ( 20 20 ) MASK 031 VIA1_2 '''
        >>> point = Lark(NET_GRAMMAR, parser='lalr', start='routing_point', transformer=NetTransformer()).parse(data)
        >>> point
        (10,10) -> (20,*) -> (20,20) -> VIA1_2
        """
        return RoutingPoint(starting_point, [x for x in others], metal_layer=None)

    @v_args(inline=True)
    def new_statement(self, *args) -> RoutingPoint:
        """
        >>> data = ''' NEW metal2 TAPER STYLE 20 ( 275690 21980 ) ( * 22260 ) via2_5 ( 27000 * )'''
        >>> rp = Lark(NET_GRAMMAR, parser='lalr', start='new_statement', transformer=NetTransformer()).parse(data)
        >>> rp
        (275690,21980) -> (*,22260) -> via2_5 -> (27000,*)
        >>> rp.normalize()
        >>> rp
        (275690,21980) -> (275690,22260) -> via2_5 -> (27000,22260)
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
        >>> wiring = Lark(NET_GRAMMAR, parser='lalr', start='regular_wiring', transformer=NetTransformer()).parse(data) 
        >>> wiring # doctest: +NORMALIZE_WHITESPACE
        (283290,22260) -> (*,22820) -> via2_8 --> 
        (282910,22820) -> (*,23380) --> 
        (278730,23380) -> (*,23660) --> 
        (267710,23380) -> (*,23660) --> 
        (266950,23660) -> (*,24500) -> via1_4
        >>> wiring.normalize()
        >>> wiring # doctest: +NORMALIZE_WHITESPACE
        (283290,22260) -> (283290,22820) -> via2_8 --> 
        (282910,22820) -> (282910,23380) --> 
        (278730,23380) -> (278730,23660) --> 
        (267710,23380) -> (267710,23660) --> 
        (266950,23660) -> (266950,24500) -> via1_4
        >>> [x.metal_layer for x in wiring.routing_points]
        ['metal2', 'metal3', 'metal3', 'metal3', 'metal2']
        """
        initial_metal_layer = self.get_token(tree, "LAYER_NAME")[0].value
        routing_points = list(filter(lambda x: isinstance(x,RoutingPoint), tree.children))
        routing_points[0].set_metal_layer(initial_metal_layer)

        return NetWiring(routing_points)

    def regular_wirings(self, list_of_net_wirings: List[NetWiring]) -> List[NetWiring]:
        return list_of_net_wirings
    
    @v_args(inline=True)
    def component_and_pin(self, component_name: str, pin_name: str, synthesized: str = None) -> ComponentAndPort:
        """
        >>> data = ''' top_core/submodule_a/submodule_b INPUT1 '''
        >>> Lark(NET_GRAMMAR, parser='lalr', start='component_and_pin', transformer=NetTransformer()).parse(data) 
        top_core/submodule_a/submodule_b/INPUT1
        >>> Lark(NET_GRAMMAR, parser='lalr', start='component_and_pin', transformer=NetTransformer()).parse(data).is_synthesized()
        False
        >>> data = ''' top_core/submodule_a/submodule_b INPUT1 + SYNTHESIZED '''
        >>> Lark(NET_GRAMMAR, parser='lalr', start='component_and_pin', transformer=NetTransformer()).parse(data) 
        top_core/submodule_a/submodule_b/INPUT1
        >>> Lark(NET_GRAMMAR, parser='lalr', start='component_and_pin', transformer=NetTransformer()).parse(data).is_synthesized()
        True
        >>> data = ''' PIN pepegius_megistus + SYNTHESIZED '''
        >>> Lark(NET_GRAMMAR, parser='lalr', start='component_and_pin', transformer=NetTransformer()).parse(data)
        PIN pepegius_megistus
        >>> Lark(NET_GRAMMAR, parser='lalr', start='component_and_pin', transformer=NetTransformer()).parse(data).is_synthesized()
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
        >>> Lark(NET_GRAMMAR, parser='lalr', start='header', transformer=NetTransformer()).parse(data)
        top_core/submodule_a/net3: top_core/submodule_a/register_\[3\]/CK -- top_core/submodule_a/register_\[2\]/CK -- PIN IN1
        >>> data = ''' MUSTJOIN ( top_core/submodule_w PIN5 ) '''
        >>> Lark(NET_GRAMMAR, parser='lalr', start='header', transformer=NetTransformer()).parse(data)
        MUSTJOIN: top_core/submodule_w/PIN5
        """
        return NetHeader(pin_name_or_join, [x for x in args])    

    @v_args(tree=True) 
    def virtual_pin(self, tree):
        """
        >>> data = '''+ VPIN M7K.v2 LAYER M2 ( -10 -10 ) ( 10 10 ) FIXED ( 10 10 ) FS'''
        >>> test = Lark(NET_GRAMMAR, parser='lalr', start='virtual_pin', transformer=NetTransformer()).parse(data) 
        >>> test
        VPIN: M7K.v2 ((-10,-10),(10,10))
        >>> test.get_metal_layer()
        'M2'
        >>> test.get_placement()
        ('FIXED', (10,10), 'FS')
        >>> data = '''+ VPIN M7K.v2 LAYER M2 ( -10 -10 ) ( 10 10 ) FIXED ( 10 10 ) S'''
        >>> test = Lark(NET_GRAMMAR, parser='lalr', start='virtual_pin', transformer=NetTransformer()).parse(data) 
        >>> test
        VPIN: M7K.v2 ((-10,-10),(10,10))
        >>> data = '''+ VPIN M7K.v2 ( -10 -10 ) ( 10 10 ) '''
        >>> Lark(NET_GRAMMAR, parser='lalr', start='virtual_pin', transformer=NetTransformer()).parse(data) 
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
        >>> Lark(NET_GRAMMAR, parser='lalr', start='virtual_pins', transformer=NetTransformer()).parse(data) 
        [VPIN: M7K.v2 ((-10,-10),(10,10)), VPIN: M7K.v3 ((-13,12),(50,70)), VPIN: M7K.v2 ((-134,-10),(10,14))]
        """
        return list_of_virtual_pins
    
    def net_properties(self, list_of_property: List[Property]) -> List[Property]:
        """
        >>> data = ''' + PROPERTY PROPERTYF 2
        ... + PROPERTY PROPERTYG 5'''
        >>> Lark(NET_GRAMMAR, parser='lalr', start='net_properties', transformer=NetTransformer()).parse(data) 
        [Property(name='PROPERTYF', value='2'), Property(name='PROPERTYG', value='5')]
        """
        return list_of_property

    @v_args(inline=True)
    def net_property(self, name: str, value: str) -> Property: 
        """
        >>> data = '''+ PROPERTY PROP onE'''
        >>> Lark(NET_GRAMMAR, parser='lalr', start='net_property', transformer=NetTransformer()).parse(data) 
        Property(name='PROP', value='onE')
        """
        return Property(str(name), str(value))

    @v_args(tree=True)
    def net_statement(self, tree) :
        """
        >>> data = '''- u_ibex_core/ex_block_i/gen_multdiv_fast_multdiv_i/n2491
        ... ( u_ibex_core/ex_block_i/gen_multdiv_fast_multdiv_i/U2374 A )
        ... ( u_ibex_core/ex_block_i/gen_multdiv_fast_multdiv_i/U2348 CO )
        ... + SHIELDNET NET3
        ... + SHIELDNET NET4
        ... + VPIN M7K.v2 LAYER M2 ( -10 -10 ) ( 10 10 ) FIXED ( 10 10 ) FS
        ... + VPIN M7K.v3 LAYER M2 ( -13 12 ) ( 50 70 ) FIXED ( 10 10 ) N
        ... + VPIN M7K.v2 LAYER M2 ( -134 -10 ) ( 10 14 )
        ... + XTALK 200 
        ... + ROUTED metal3 ( 252170 114660 ) ( 252510 * ) via2_5
        ... NEW metal4 ( 252170 113820 ) ( * 114660 ) via3_2
        ... NEW metal5 ( 249370 113820 ) ( 252170 * ) via4_0
        ... NEW metal6 ( 249370 102620 ) ( * 113820 ) via5_0 
        ... + SOURCE DIST 
        ... + FIXEDBUMP
        ... + FREQUENCY 42.0
        ... + ORIGINAL net2
        ... + USE POWER 
        ... + PATTERN STEINER
        ... + ESTCAP 30.0
        ... + WEIGHT 2
        ... + PROPERTY PROP2 K
        ... + PROPERTY PROP3 F ;'''
        >>> Lark(NET_GRAMMAR, parser='lalr', start='net_statement', transformer=NetTransformer()).parse(data) 
        u_ibex_core/ex_block_i/gen_multdiv_fast_multdiv_i/n2491
        >>> data = '''- u_ibex_core/instr_req_gated
        ... ( u_ibex_core/U19 ZN )
        ... ( u_ibex_core/if_stage_i/gen_prefetch_buffer_prefetch_buffer_i/U161 A )
        ... ;'''
        >>> test = Lark(NET_GRAMMAR, parser='lalr', start='net_statement', transformer=NetTransformer()).parse(data) 
        >>> test 
        u_ibex_core/instr_req_gated
        >>> data = ''' - hart_id_i[31]
        ... ( PIN hart_id_i[31] ) ( u_ibex_core/cs_registers_i/U877 A2 )
        ... + ROUTED metal1 ( 91390 309820 ) ( 93290 * 0 )
        ...   NEW metal3 ( 80810 313180 ) ( 91390 * ) via2_5
        ...   NEW metal3 ( 14630 335020 ) ( 80810 * ) via3_2
        ...   NEW metal1 ( 13870 335020 ) ( 14630 * ) via1_7
        ...   NEW metal1 ( 70 335020 0 ) ( 950 * )
        ...   NEW metal1 ( 950 335020 ) ( * 335300 )
        ...   NEW metal1 ( 950 335300 ) ( 13870 * )
        ...   NEW metal1 ( 13870 335020 ) ( * 335300 )
        ...   NEW metal4 ( 80810 313180 ) ( * 335020 )
        ...   NEW metal2 ( 91390 309820 ) ( * 313180 )
        ...   NEW metal3 ( 14630 335020 ) via2_5
        ...   NEW metal4 ( 80810 313180 ) via3_2
        ...   NEW metal2 ( 91390 309820 ) via1_7 ; '''
        >>> Lark(NET_GRAMMAR, parser='lalr', start='net_statement', transformer=NetTransformer()).parse(data) 
        hart_id_i[31]
        >>> data = ''' - u_ibex_core/ex_block_i/alu_i/alu_32bit_adder/n166
        ... ( u_ibex_core/ex_block_i/alu_i/alu_32bit_adder/U145 A2 )
        ... ( u_ibex_core/ex_block_i/alu_i/alu_32bit_adder/U144 ZN )
        ... + ROUTED metal2 ( 248710 170940 ) ( * 173460 )
        ...   NEW metal2 ( 247950 173460 ) ( * 175980 )
        ...   NEW metal2 ( 247570 175980 ) ( * 178500 ) via1_7
        ...   NEW metal2 ( 247570 175980 ) ( 247950 * )
        ...   NEW metal2 ( 247950 173460 ) ( 248710 * )
        ...   NEW metal2 ( 248710 170940 ) via1_7
        ... ;'''
        >>> net = Lark(NET_GRAMMAR, parser='lalr', start='net_statement', transformer=NetTransformer()).parse(data) 
        >>> net
        u_ibex_core/ex_block_i/alu_i/alu_32bit_adder/n166
        >>> print(net.routing_points) # doctest: +NORMALIZE_WHITESPACE
        [(248710,170940) -> (248710,173460), 
        (247950,173460) -> (247950,175980), 
        (247570,175980) -> (247570,178500) -> via1_7, 
        (247570,175980) -> (247950,175980), 
        (247950,173460) -> (248710,173460), 
        (248710,170940) -> via1_7]
        
        """

        def _find_str_option(option: str, cast_to: object = str) -> Union[None,str]:
            tree_tokens = tree.children
            string_options = list(filter(lambda x: isinstance(x, str), tree_tokens))

            for opt in string_options:
                if option in opt: 
                    return cast_to(opt.split()[-1])
                
            return None 
        
        def _has_attribute(container_type: object, values_type: object) -> Union[None,List[object]]:

            tree_tokens = tree.children
            containers = list(filter(lambda x: isinstance(x, container_type), tree_tokens))

            if not containers: 
                return None
 
            for container in containers:
                
                if len(container) > 0 and all([isinstance(x, values_type) for x in container]): 
                    return container
                
            return None 
        
        name = tree.children[0]

        net = Net(name, 
            shield_nets = _has_attribute(list, str),
            virtual_pins= _has_attribute(list, VirtualPin),
            xtalk= _find_str_option("XTALK", int),
            non_default_rule = _find_str_option("NONDEFAULTRULE"),
            regular_wirings=_has_attribute(list, NetWiring),
            source=_find_str_option("SOURCE"),
            fixed_bump=_find_str_option("FIXEDBUMP", bool),
            frequency=_find_str_option("FREQUENCY", float),
            original_net=_find_str_option("ORIGINAL"),
            use=_find_str_option("USE"),
            pattern=_find_str_option("PATTERN"),
            estimated_capacitance=_find_str_option("ESTCAP", float),
            weight=_find_str_option("WEIGHT", int),
            properties=_has_attribute(list, Property))
        
        net.normalize()
        net._set_point_list()
        net._set_routing_points()
        return net 
    
    def net_statements(self, list_of_nets : List[Net]) -> List[Net]:
        return list_of_nets

    shield_nets = lambda self, vals : list(map(str,vals))
    non_default_rule = lambda self, token : f"NONDEFAULTRULE {str(token[0].value)}"
    estimated_capacitance = lambda self, token : f"ESTCAP {float(token[0].value)}"
    original_net = lambda self, token : f"ORIGINAL {str(token[0].value)}"
    weight = lambda self, token : f"WEIGHT {int(token[0].value)}" 
    pattern = lambda self, token : f"PATTERN {token[0].value}"
    use = lambda self, token : f"USE {token[0].value}"
    source = lambda self, token : f"SOURCE {token[0].value}"
    fixed_bump = lambda self, _ : f"FIXEDBUMP True"
    xtalk = lambda self, token : f"XTALK {token[0].value}"
    frequency = lambda self, token : f"FREQUENCY {float(token[0].value)}"

def parse_nets_section(data: str) -> List[Net]:

    return Lark(NET_GRAMMAR, parser='lalr', start='net_statements', transformer=NetTransformer()).parse(data) 
