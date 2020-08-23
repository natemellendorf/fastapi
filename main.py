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
import time
import asyncio
import uvicorn
from random import randint

import concurrent.futures


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
    print(f"\n---\nIN THREAD:\n{message.value}")
    z = randint(0, 10)
    print(f"Sleeping for: {str(z)}")
    time.sleep(z)
    print(f"{message.value} is now AWAKE\n---\n")
    return(f"{message.value}")


if environ.get("KAFKA_NODE"):
    # Run as Kafka consumer
    print("Starting Kafka consumer...\n")

    consumer = KafkaConsumer(
        "test",
        auto_offset_reset="earliest",
        enable_auto_commit=True,
        group_id="fastapi",
        value_deserializer=lambda m: loads(m.decode("utf-8")),
        bootstrap_servers=["10.10.0.230:32780"],
    )

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
                    print(f"---\nRETURNED:\n{origional_task} - {completed_task.result()}\n---\n")


elif __name__ == "__main__":
    # Run as API
    uvicorn.run("main:app", host="0.0.0.0", port=8000, log_level="info")
