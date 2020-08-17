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
import asyncio

app = FastAPI()


class Item(BaseModel):
    hostname: str
    username: str
    password: str
    platform: str
    config: str


async def task():
    print("Example async task")


async def repeat_task():
    while True:
        await asyncio.sleep(5)
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
