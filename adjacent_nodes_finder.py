'''
@ Author: ZhouCH
@ Date: Do not edit
LastEditors: Please set LastEditors
LastEditTime: 2023-02-18 19:41:58
@ FilePath: Do not edit
@ Description: 
@ License: MIT
'''

from lark import Lark

# with open('ibex_top_working.def', 'rt', encoding='utf-8') as input_file:
#     data = input_file.read()

# net_input = data[data.find("NETS") + 4 : data.find("END NETS")]
l = Lark('''start: WORD "," WORD "!"

            %import common.WORD   // imports from terminal library
            %ignore " "           // Disregard spaces in text
         ''')

print( l.parse("Hello, World!") )