from os import environ
from fastapi import FastAPI, Header, Depends
from typing import Optional
from nornir import InitNornir
from nornir.plugins.tasks.networking import (
    netmiko_send_command,
    napalm_configure,
    napalm_get,
    netmiko_send_config,
    netmiko_save_config,
)
from nornir.plugins.functions.text import print_result
from pydantic import BaseModel

app = FastAPI()


class Item(BaseModel):
    """
    hostname: FQDN or IP of device\n
    username: Username to access the device\n
    password: Password to access the device\n
    platform: <a href="https://napalm.readthedocs.io/en/latest/support/">NAPALM plugin for the device</a>\n
    config: Configuration to apply to the device\n
    """

    hostname: str
    username: str
    password: str
    platform: str
    config: str


def change_host_data(host):
    """
    Change device information as needed
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
    config = kwargs["config"]

    task.run(
        name="Junos - Apply Config", task=napalm_configure, configuration=config,
    )


def junos_get_config(task, **kwargs):
    task.run(name="Junos - Get Info", task=napalm_get, getters=["get_facts"])


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/user")
async def get_current_user(x_vouch_user: Optional[str] = Header(None)):
    return {"X-Vouch-User": x_vouch_user}


@app.post("/set/fw/hostname")
def set_fw_hostname(data: Item, x_vouch_user: Optional[str] = Header(None)):

    output = {}
    output["Requester"] = x_vouch_user

    data.config = f"""
    system {{host-name example;}}
    """

    r = init_nornir(tasks=[junos_update_config], config=data.config)

    for host, task_results in r.items():
        # print(task_results[1].diff)
        output[host] = task_results[1].diff

    return {"Result": output}


@app.get("/get/fw/hostname")
def get_fw_hostname(x_vouch_user: Optional[str] = Header(None)):

    output = {}
    output["Requester"] = x_vouch_user

    r = init_nornir(tasks=[junos_get_config])

    for host, task_results in r.items():
        facts = task_results[1].result
        # print(facts["get_facts"]["hostname"])
        sn = facts["get_facts"].get("serial_number")
        hostname = facts["get_facts"].get("hostname")

        output[host] = {}
        output[host]["serial_number"] = sn
        output[host]["hostname"] = hostname

    return {"Result": output}
