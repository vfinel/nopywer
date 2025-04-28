import yaml


def get_user_parameters():
    with open("user_parameters.yaml", "r") as file:
        param = yaml.safe_load(file)

    return param
