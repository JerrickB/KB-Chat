
from os import environ
from yaml import safe_load
from pathlib import Path

def load_config(file_path: str = str(Path(__file__).parent.parent.parent / "config.yml")):
    """
    Load configuration file into environment variables.

    This function loads the configuration file specified by `file_path` into
    environment variables. The configuration file iskept separately for ease of access, and is expected to be in YAML format.

    :param file_path: Path to configuration file. Default: '../config.yml'
    """
    # Open the configuration file
    with open(file_path, 'r') as file:
        # Load the configuration file into a dictionary
        config = safe_load(file)
        # Update the environment variables with the configuration values
        environ.update(config)
