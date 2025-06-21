import logging

# Create a logger
logger = logging.getLogger()  # "my_application")  # can use __name__ too

# Set basic logger level to DEBUG
logger.setLevel(logging.DEBUG)

# create formatters
console_formatter = logging.Formatter("%(message)s")
file_formatter = logging.Formatter("%(levelname)s - %(message)s")  # %(asctime)s -

# create handlers
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)  # Change to DEBUG for detailed logs
console_handler.setFormatter(console_formatter)

file_handler = logging.FileHandler("app.log")
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(file_formatter)

# add loggers
logger.addHandler(console_handler)
logger.addHandler(file_handler)
