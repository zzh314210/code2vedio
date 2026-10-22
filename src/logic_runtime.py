"""Load only the trusted renderer/compiler snapshot created by initialize_project.

The surrounding project fingerprint is checked before planning or rendering.
Uploaded Python files are never considered, and filenames are not model inputs.
"""
import importlib.util
from execution import validate_output


def load_runtime(project):
    def load(name):
        file=validate_output(project,project/'code/runtime'/f'{name}.py')
        spec=importlib.util.spec_from_file_location(f'_frozen_{name}_{project.name}',file)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        return module
    contract=load('logic_contract');renderer=load('logic_renderer')
    # Keep the snapshot renderer attached to its own compiler, not a later
    # deployment's lesson wording or validation rules.
    for name in ('digest','describe','validate_plan_handoff'):
        setattr(renderer,name,getattr(contract,name))
    return contract,renderer
