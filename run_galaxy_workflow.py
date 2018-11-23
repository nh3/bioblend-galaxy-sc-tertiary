#!/usr/bin/env python
"""run_galaxy_workflow
"""

import argparse
import logging
import os.path
import re
import time
import yaml
from bioblend.galaxy import GalaxyInstance


def get_args():
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument('-C', '--conf',
                            required=True,
                            help='A yaml file describing the workflow')
    arg_parser.add_argument('-I', '--instance',
                            default='__default',
                            help='Galaxy server instance name')
    arg_parser.add_argument('-H', '--history',
                            default='scanpy',
                            help='Name of the history to create')
    arg_parser.add_argument('-V', '--variable',
                            default=[],
                            help='A list of tool parameters to vary')
    arg_parser.add_argument('--debug',
                            action='store_true',
                            default=False,
                            help='Print debug information')
    args = arg_parser.parse_args()
    return args


def set_logging_level(debug=False):
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.WARNING,
        format=('%(asctime)s; %(levelname)s; %(filename)s; %(funcName)s(): '
                '%(message)s'),
        datefmt='%y-%m-%d %H:%M:%S')


def get_instance(name='__default'):
    with open(os.path.expanduser('~/.parsec.yml'), mode='r') as fh:
        data = yaml.load(fh)
    assert name in data, 'unknown instance'
    entry = data[name]
    if isinstance(entry, dict):
        return entry
    else:
        return data[entry]


def read_workflow_from_file(filename):
    with open(filename, mode='r') as fh:
        wf = yaml.load(fh)
    return wf


def validate_workflow_tools(wf, tools):
    tool_ids = set([tl['id'] for tl in tools])
    for tool in wf['steps']:
        assert tool['id'] in tool_ids, "unknown tool: {}".format(tool['id'])
    return True


def main():
    args = get_args()
    set_logging_level(args.debug)

    # Prepare environment
    ins = get_instance(args.instance)
    wf = read_workflow_from_file(args.conf)
    gi = GalaxyInstance(ins['url'], key=ins['key'])
    tools = gi.tools.get_tools()
    validate_workflow_tools(wf, tools)

    # Create new history to run workflow
    history = gi.histories.create_history(name=args.history)

    # Run each
    for i, tool in enumerate(wf['steps']):
        logging.info(tool['id'])
        # tool is a dict: {'id':str, 'inputs':[], 'outputs':{}}
        for _input in tool['inputs']:
            value = tool['inputs'][_input]
            if not isinstance(value, str):
                continue
            matched = re.match(r'(\d+)\|(\w+)', value)
            if matched:
                step_idx, output_name = matched.groups()
                step_idx = int(step_idx)
                assert step_idx < i, "Step index out of range"
                prev_tool = wf['steps'][step_idx]
                assert output_name in prev_tool['outputs'], (
                    "requested output not found: {}".format(output_name))
                tool['inputs'][_input] = prev_tool['outputs'][output_name]
        # gi.tools.run_tool returns a dict 'job'
        job = gi.tools.run_tool(history['id'], tool['id'], tool['inputs'])
        # job['outputs'] is a list of dict,
        # useful items are 'output_name' and 'id'
        for _output in job['outputs']:
            output_name = _output['output_name']
            if output_name in tool['outputs']:
                tool['outputs'][output_name] = {'src': 'hda',
                                                'id': _output['id']}
        # wait for a little while between each job submission
        time.sleep(5)

    return 0


if __name__ == '__main__':
    main()
