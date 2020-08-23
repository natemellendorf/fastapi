from os import environ
from fastapi import FastAPI, Header
from typing import Optional
from nornir import InitNornir
from nornir.plugins.tasks.networking import (
    netmiko_send_command,
    napalm_configure,
    napalm_get,
    netmiko_send_config,
)
from nornir.plugins.functions.text import print_result
from pydantic import BaseModel
from kafka import KafkaConsumer
from json import loads

import logging
import time
import asyncio
import uvicorn
from random import randint
import concurrent.futures

formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')

def setup_logger(name, log_file, level=logging.INFO):
    """
    Configure logging for the app
    """

    handler_file = logging.FileHandler(log_file)
    handler_file.setFormatter(formatter)
    handler_stream = logging.StreamHandler() 
    handler_stream.setFormatter(formatter)

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.addHandler(handler_file)
    logger.addHandler(handler_stream)

    return logger

logger_general = setup_logger('general', 'general.log')
logger_fastapi = setup_logger('fastapi', 'fastapi.log')
logger_kafka = setup_logger('kafka', 'kafka.log')

app = FastAPI()


class Item(BaseModel):
    hostname: str
    username: str
    password: str
    platform: str
    config: str


async def task():
    t = time.localtime()
    current_time = time.strftime("%H:%M:%S", t)
    print(current_time)


async def repeat_task():
    while True:
        await asyncio.sleep(60)
        await task()


@app.on_event("startup")
def repeated_task():
    """
    Create a background task to run with FastAPI
    """

    asyncio.create_task(repeat_task())


def change_host_data(host):
    """
    Change device information for demo
    """

    host.username = environ.get("FAST_USERNAME")
    host.password = environ.get("FAST_PASSWORD")
    host.hostname = environ.get("FAST_HOSTNAME")
    host.platform = environ.get("FAST_PLATFORM")


def init_nornir(tasks: list, dry_run: bool = True, **kwargs):
    """
    Create a Nornir instance and run tasks
    """

    for task in tasks:

        nr = InitNornir(
            core={"num_workers": 4},
            dry_run=dry_run,
            inventory={
                "plugin": "nornir.plugins.inventory.simple.SimpleInventory",
                "options": {"host_file": "templates/hosts.yml"},
                "transform_function": change_host_data,
            },
        )

        r = nr.run(task, config=kwargs.get("config"))
        print_result(r)

        return r


def junos_update_config(task, **kwargs):
    """
    Apply config to Junos device
    """

    config = kwargs["config"]

    task.run(
        name="Junos - Apply Config", task=napalm_configure, configuration=config,
    )


def junos_get_config(task, **kwargs):
    """
    Get facts from Junos device
    """

    task.run(name="Junos - Get Info", task=napalm_get, getters=["get_facts"])


@app.get("/")
async def root():
    return {"message": "Hello, World!"}


@app.get("/user")
async def get_current_user(x_vouch_user: Optional[str] = Header(None)):
    """
    Get the username for the logged in user
    """

    return {"X-Vouch-User": x_vouch_user}


@app.post("/set/fw/hostname")
def set_fw_hostname(data: Item, x_vouch_user: Optional[str] = Header(None)):
    """
    Change the hostname of the demo Junos device\\
    **DEMO**: Device and config changes are hard set by API

    - **hostname**: FQDN or IP of device
    - **username**: Username to access the device
    - **password**: Password to access the device
    - **platform**: <a href="https://napalm.readthedocs.io/en/latest/support/">NAPALM plugin for the device</a>\n
    - **config**: Configuration to apply to the device
    """

    output = {}
    output["Requester"] = x_vouch_user

    data.config = f"""
    system {{host-name example;}}
    """

    r = init_nornir(tasks=[junos_update_config], config=data.config)

    for host, task_results in r.items():
        output[host] = task_results[1].diff

    return {"Result": output}


@app.get("/get/fw/hostname")
def get_fw_hostname(x_vouch_user: Optional[str] = Header(None)):
    """
    Get the hostname of the demo Junos device
    """

    output = {}
    output["Requester"] = x_vouch_user

    r = init_nornir(tasks=[junos_get_config])

    for host, task_results in r.items():
        facts = task_results[1].result
        hostname = facts["get_facts"].get("hostname")

        output[host] = {}
        output[host]["hostname"] = hostname

    return {"Result": output}


# Kafka Event Logic
def print_message(message):
    logger_kafka.info(f"\n---\nIN THREAD:\n{message.value}")
    z = randint(0, 10)
    logger_kafka.info(f"Sleeping for: {str(z)}")
    time.sleep(z)
    logger_kafka.info(f"{message.value} is now AWAKE\n---\n")
    return(f"{message.value}")


def start_kafka_consumer(kafka_server):
    """
    Function to establish a connection to requested Kafka servers.
    Subscribe to the requested topic with the group_id: fastapi.
    Poll Kafka for new messages.
    Upon new message, create thread and perform logic on message.
    """

    def init_consumer():

        gatekeeper = False

        while gatekeeper is False:

            try:
                # Establish connection with Kafka
                consumer = KafkaConsumer(
                    "test",
                    auto_offset_reset="earliest",
                    enable_auto_commit=True,
                    group_id="fastapi",
                    value_deserializer=lambda m: loads(m.decode("utf-8")),
                    bootstrap_servers=[kafka_server],
                )

                gatekeeper = True
            
            except Exception as e:
                logger_kafka.info(f"Unable to connect to Kafka:\n{e}\nRetry in 10 sec...")
                time.sleep(10)

    consumer = init_consumer()        

    # Construct executor for future threading
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=32, thread_name_prefix="thread"
    ) as executor:

        # Create infinite loop to poll Kafka for events
        while True:
            # Poll Kafka for new events
            msg_pack = consumer.poll(timeout_ms=500)
            # Deconstruct returned Kafka event
            for tp, messages in msg_pack.items():
                # For each message in the event..
                for message in messages:
                    # Create a new thread to process the message
                    thread_result = {executor.submit(print_message, message): message}
                # Results are returned out of order, so we map them here
                for completed_task in concurrent.futures.as_completed(thread_result):
                    origional_task = thread_result[completed_task]
                    logger_kafka.info(f"---\nRETURNED:\n{origional_task} - {completed_task.result()}\n---\n")
                    


def start_app(app):
    """
    Function to determine which logic to start.
    KAFKA_NODE: Start the Kafka consumer logic.
    FAST_API: Start the FastAPI logic.
    """

    if app == "KAFKA_NODE":
        logger_general.info("Stating: Kafka Node")
        kafka_server = environ.get("KAFKA_SERVER")
        start_kafka_consumer(kafka_server)

    elif app == "FAST_API":
        logger_general.info("Stating: FastAPI")
        uvicorn.run("main:app", host="0.0.0.0", port=8000, log_level="info")

# ----------
# App SOF
# ----------
if __name__ == "__main__":

    # Construct a list of processes to start
    # FastAPI is injected by default
    apps=["FAST_API"]

    # If KAFKA_NODE, append to process list
    if environ.get("KAFKA_NODE") and environ.get("KAFKA_SERVER"):
        apps.append("KAFKA_NODE")

    # Construct executor for future processing
    with concurrent.futures.ProcessPoolExecutor(
        max_workers=2 ) as processor:

        # Use list comprehension to create new processes
        for number, prime in zip(apps, processor.map(start_app, apps)):
            print(f"{number} -> {prime}" % (number, prime))
