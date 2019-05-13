import importlib

import hypothesis.strategies as st
import numpy as np
import hypothesis.extra.numpy as npst
import re

from ros_basic_strategies import array, string, time, duration
try:
    import rospy
    import rosmsg
    import rospkg
except ImportError:
    print "Please install ROS first"


def ros_msg_loader(msg_type):
    pattern = re.compile(r'([\w]+)\/([\w]+)')
    match = pattern.search(msg_type)
    if match:
        module_name = match.group(1) + '.msg'
        class_name = match.group(2)
        module = importlib.import_module(module_name)
        msg_class = module.__dict__[class_name]
        if not msg_class:
            raise ImportError
        else:
            return msg_class
    else:
        raise ImportError


def ros_msg_list():
    msg_list = []
    ros_pack = rospkg.RosPack()
    packs = sorted([x for x in rosmsg.iterate_packages(ros_pack, rosmsg.MODE_MSG)])
    for (p, path) in packs:
        for file in rosmsg.list_types(p):
            msg_list.append(file.split('/')[1])
    return msg_list


def check_msg_type(msg_list, msg_str):
    if msg_str in msg_list:
        return True
    return False


def create_publisher(topic, msg_type):
    pub = rospy.Publisher(topic, msg_type, queue_size=10)
    rospy.init_node('fuzzer_node', anonymous=False)
    return pub


def map_ros_types(ros_class):
    strategy_dict = {}
    slot_names = ros_class.__slots__
    slot_types = ros_class._slot_types
    slots_full = list(zip(slot_names, slot_types))
    for s_name, s_type in slots_full:
        try:
            if '[' and ']' in s_type:
                parse_basic_arrays(s_name, s_type, strategy_dict)
            elif s_type is 'string':
                strategy_dict[s_name] = st.text()
            elif s_type is 'time':
                strategy_dict[s_name] = time()
            elif s_type is 'duration':
                strategy_dict[s_name] = duration()
            else:  # numpy compatible ROS built-in types
                strategy_dict[s_name] = npst.from_dtype(np.dtype(s_type))
        except TypeError:
            parse_complex_types(s_name, s_type, strategy_dict)
    return dynamic_strategy_generator_ros(ros_class, strategy_dict)


def parse_basic_arrays(s_name, s_type, strategy_dict):
    array_size = s_type[s_type.index('[') + 1:s_type.index(']')]
    if array_size == '':
        array_size = None  # TODO: not None!
    else:
        array_size = int(array_size)
    aux = s_type.split('[')[0]
    if aux == 'string':
        strategy_dict[s_name] = array(elements=string(), min_size=array_size, max_size=array_size)
    else:
        strategy_dict[s_name] = array(elements=npst.from_dtype(np.dtype(aux)), min_size=array_size,
                                      max_size=array_size)


def parse_complex_types(s_name, s_type, strategy_dict):
    # TODO: Complex type arrays
    if '/' in s_type and '[]' not in s_type:
        strategy_dict[s_name] = map_ros_types(ros_msg_loader(s_type))
    elif '/' in s_type and '[]' in s_type:
        # TODO: Implement complex types fixed value arrays
        s_type_fix = s_type.split('[')[0]  # e.g. std_msgs/Header take just Header
        strategy_dict[s_name] = array(elements=map_ros_types(ros_msg_loader(s_type_fix)))


# A better approach. It returns an instance of a ROS msg directly, so no need for mapping! :)
@st.composite
def dynamic_strategy_generator_ros(draw, ros_class, strategy_dict):  # This generates existing ROS msgs objects
    aux_obj = ros_class()
    for key, value in strategy_dict.iteritems():
        setattr(aux_obj, key, draw(value))
    return aux_obj
