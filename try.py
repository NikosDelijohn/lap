# import argparse as ap

# param_parser=ap.ArgumentParser(
#     prog="try.py",
#     description="This file is intended to parse the NETS segment of the '.def' file. \
#         It accepts the name of target functional unit to filter other unexpected nodes",
#     epilog=None
# )

# param_parser.add_argument("-fu","--functional_unit",
#                             action="store",
#                             choices=["adder", "decoder", "compressed_decoder", "lsu"],
#                             help="This argument specifies the targeted functional unit, \
#                                 if 'None' is the param, the program will add all the nodes of the processor.",
#                             required=False
#                             )
# param_parser.add_argument('-f', "--file_name",
#                             action='store',
#                             help="This argument indicates a 'xxx.def' file, or a text file with NETS segment.",
#                             required=True,
#                             metavar="xxx.def"
#                             )  # on/off flag
# param_parser.add_argument('-of','--output_file',
#                             action='store',
#                             help="this argument indicetes the output file 'xxx.map' of the program, \
#                             default value is 'pair.map'",
#                             default="pair.map",
#                             metavar="xxx_pair.map")

# arg=param_parser.parse_args()

# # print(type(arg.functional_unit), type(arg.file_name))
# print(arg.output_file)

###########################################################################################

# from lark import Lark
# from lark import Transformer

# class data_transformer(Transformer):
#     def net_list(self, nets):
#         return dict(nets)
    
#     def net(self, net_info):
#         net_name, other_info=net_info[0], net_info[1:]
#         return net_name, other_info
    
#     def NET_NAME(self, name):
#         return str(name[0])
    
#     def PIN_NAME(self, name):
#         return str(name[0])
    
#     def net_aliasing_list(self, alias_list):
#         return dict(alias_list)
    
#     def net_name_alias(self, alias_pair):
#         path, name=alias_pair[0], alias_pair[1] 
#         return path, name
        
#     def COMPONENT_PATH(self, path):
#         return str(path[0])

#     def net_alias(self, name):
#         return str(name[0])
    
#     def regular_wiring_statement(self, wire_list):
#         return list(wire_list)
    
#     def wire(self, wire_info):
#         tp, layer, coordinate=wire_info[0], wire_info[1], [wire_info[2], wire_info[3]]
#         return tp, layer, coordinate
    
#     def WIRE_TYPE(self, tp):
#         return str(tp)
    
#     def layer(self, l):
#         return str(l[0])
    
#     def X(self, n):
#         return str(n[0])
    
#     def Y(self, n):
#         return str(n[0])
    
# net_grammar=r"""
#     net_list: net*

#     net: "-" NET_NAME ["(" "PIN" PIN_NAME ")"] net_aliasing_list ["+" regular_wiring_statement] ";"
#     NET_NAME: /(\w|\/|\[|\])+/
#     PIN_NAME: /(\w)+\[[0-9]+\]/

#     //net_name_alias
#     net_aliasing_list: net_name_alias*
#     net_name_alias: "(" COMPONENT_PATH net_alias ")"
#     COMPONENT_PATH: /(\w|\/)+/
#     net_alias: CNAME

#     regular_wiring_statement: (wire)+ 
#     wire: WIRE_TYPE layer "(" X Y EXT_VAL? ")" ["(" X_ Y_ EXT_VAL_? ")"] [via_name]  
#     WIRE_TYPE: ("ROUTED"|"NEW")~1
#     layer: CNAME
#     X: (NUMBER|"*")+
#     Y: (NUMBER|"*")+
#     EXT_VAL: (NUMBER|"*")+
#     X_: (NUMBER|"*")+
#     Y_: (NUMBER|"*")+
#     EXT_VAL_: (NUMBER|"*")+
#     via_name: CNAME

#     %import common.SIGNED_NUMBER    
#     %import common.NUMBER           
#     %import common.CNAME            
#     %import common.WS
#     %ignore WS
#     """
# with open("try.txt", "r") as input_file:
#     data = input_file.read()
# net_input = data[data.find("NETS") + 13 : data.find("END NETS")]
# net_parser = Lark(net_grammar, start='net_list')
# net_data = net_parser.parse(net_input)
# print(net_data.pretty())

###########################################################################################
pattern='abc'
stri="ababcdcd"
if pattern in stri:
    print("5555")