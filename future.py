#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2024/01/13 12:59
# @File    : future.py
# @Author  : donghaixing
# Do have a faith in what you're doing.
# Make your life a story worth telling.


import os
import json
import datetime

import yaml
import requests
from loguru import logger
from tqsdk import TqAccount, TqApi, TqAuth


BASE_DIR = os.path.dirname(__file__)


def parse_config_yaml():
    with open("config.yaml", 'r') as file:
        settings = yaml.safe_load(file)
    return settings


settings = parse_config_yaml()

BOKER_ID = settings["future"]["broker_id"]
ACCOUNT_ID = settings["future"]["account_id"]
PASSWORD = settings["future"]["password"]

SDK_USERNAME = settings["tqSDK"]["user_name"]
SDK_PASSWORD = settings["tqSDK"]["password"]

FUTURE = settings["trade"]["code"]
INIT_PRICE = settings["trade"]["init_price"]
PRICE_DIFF_STEP = settings["trade"]["price_diff_step"]
TARGET_PROFIT = settings["trade"]["target_profit"]
MAX_POSITION_RATIO = settings["trade"]["max_position_ratio"]

NOTIFICATION_URL = settings["notification"]["url"]
NOTIFICATION_DEVICE_KEY = settings["notification"]["device_key"]
NOTIFICATION_SOUND = settings["notification"]["sound"]
NOTIFICATION_ICON = settings["notification"]["icon"]
NOTIFICATION_MSG_URL = settings["notification"]["msg_url"]


def init_log():
    LOG_DIR = os.path.join(BASE_DIR, "log")
    os.makedirs(LOG_DIR, exist_ok=True)
    current_time_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
    log_file = os.path.join(LOG_DIR, f"quant_trade_{current_time_str}.log")
    logger.add(log_file)


def send_notification(data, title, category, group):
    try:
        response = requests.post(
            url=NOTIFICATION_URL,
            headers={
                "Content-Type": "application/json; charset=utf-8",
            },
            data=json.dumps({
                "body": str(data),
                "device_key": NOTIFICATION_DEVICE_KEY,
                "title": title,
                "category": category,
                "sound": NOTIFICATION_SOUND,
                "badge": 1,
                "icon": NOTIFICATION_ICON,
                "group": group,
                "url": NOTIFICATION_MSG_URL
            })
        )
        print('Response HTTP Status Code: {status_code}'.format(
            status_code=response.status_code))
        print('Response HTTP Response Body: {content}'.format(
            content=response.content))
    except requests.exceptions.RequestException:
        print('HTTP Request failed')


class FutureTask(object):
    def __init__(self):
        self.init_trade_server()

    def init_trade_server(self):
        tqacc = TqAccount(BOKER_ID, ACCOUNT_ID, PASSWORD)
        self.api = TqApi(account=tqacc, auth=TqAuth(
            SDK_USERNAME, SDK_PASSWORD))
        self.account = tqacc.get_account()
        logger.info(f"账户权益: {self.account.balance}")
        logger.info(f"可用资金: {self.account.available}")

    def insert_order(self, price):
        direction = "BUY"
        volume = 1
        order_msg = f"开仓 方向:【{direction}】数量: 【{volume}】价格: 【{price}】"

        order = self.api.insert_order(symbol=FUTURE,
                                      direction=direction, offset="OPEN", volume=volume, limit_price=price)

        send_notification(order_msg, title="开仓委托",
                          category="quant", group="future")
        logger.info(order_msg)

        while order.status != "FINISHED":
            self.api.wait_update()

        order_finished_msg = f"订单状态: {order.status}, 已成交: {order.volume_orign - order.volume_left} 手"
        send_notification(order_finished_msg, title="开仓成功",
                          category="quant", group="future")
        logger.info(order_finished_msg)

    def clearance(self, price):
        direction = "SELL"
        total_volume = self.api.get_position(FUTURE).volume_long_today
        order_msg = f"已委托平仓订单 {FUTURE} {total_volume} 手"

        order = self.api.insert_order(symbol=FUTURE,
                                      direction=direction, offset="CLOSE", volume=total_volume, limit_price=price)

        send_notification(order_msg, title="平仓委托",
                          category="quant", group="future")
        logger.info(order_msg)

        while order.status != "FINISHED":
            self.api.wait_update()

        order_finished_msg = f"恭喜您, 平仓订单已完成! 盈利: {self.account.float_profit} 元 !!!"
        send_notification(order_finished_msg, title="平仓成功",
                          category="quant", group="future")
        logger.info(order_finished_msg)

    def run(self):
        kline = self.api.get_kline_serial(FUTURE, 86400)  # 获取日内k线
        total_volume = self.api.get_position(FUTURE).volume_long_today
        logger.info(
            f"当前持仓 {FUTURE} {total_volume} 手  -->> 盈利 {self.account.float_profit} 元")
        while True:
            self.api.wait_update()
            if self.api.is_changing(kline):
                high = kline.high.iloc[-1]
                low = kline.low.iloc[-1]
                price = kline.close.iloc[-1]
                logger.info(
                    f"最新价 {price}, 最高价 {high}, 最低价 {low} -->> 当前盈利 {self.account.float_profit} 元")

                if 1 - self.account.available/self.account.balance <= MAX_POSITION_RATIO and price <= INIT_PRICE:
                    self.insert_order(price)
                    INIT_PRICE -= PRICE_DIFF_STEP

                if self.account.float_profit >= TARGET_PROFIT:
                    self.clearance(price)


if __name__ == '__main__':
    init_log()
    task = FutureTask()
    task.run()
    task.api.close()
