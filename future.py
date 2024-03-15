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
from tqsdk import TqAccount, TqApi, TqAuth, TargetPosTask


BASE_DIR = os.path.dirname(__file__)


def parse_config_yaml():
    """
    解析配置yaml文件

    :param None
    :return None
    """
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
DIRECTION = settings["trade"]["direction"]
INIT_PRICE = settings["trade"]["init_price"]
PRICE_DIFF_STEP = settings["trade"]["price_diff_step"]
VOLUME_DIFF_STEP = settings["trade"]["volume_diff_step"]
TARGET_PROFIT = settings["trade"]["target_profit"]
MAX_POSITION_RATIO = settings["trade"]["max_position_ratio"]

NOTIFICATION_URL = settings["notification"]["url"]
NOTIFICATION_DEVICE_KEY = settings["notification"]["device_key"]
NOTIFICATION_SOUND = settings["notification"]["sound"]
NOTIFICATION_ICON = settings["notification"]["icon"]
NOTIFICATION_MSG_URL = settings["notification"]["msg_url"]


def init_log():
    """
    初始化日志

    :param None
    :return None
    """
    LOG_DIR = os.path.join(BASE_DIR, "log")
    os.makedirs(LOG_DIR, exist_ok=True)
    current_time_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
    log_file = os.path.join(LOG_DIR, f"quant_trade_{current_time_str}.log")
    logger.add(log_file)


def send_notification(data, title, category, group):
    """
    通过bark推送交易通知

    :param data: dict --> 消息体字典
    :param title: str --> 消息标题
    :param category: str --> 消息分类
    :param group: str --> 消息分组
    :return None
    """
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
    """期货交易任务类"""

    def __init__(self):
        """
        任务初始化

        :param None
        :return None
        """
        self.init_trade_server()
        self.target_price = INIT_PRICE
        self.price_diff_step = PRICE_DIFF_STEP
        self.volume_diff_step = VOLUME_DIFF_STEP

    def init_trade_server(self):
        """
        初始化行情服务器

        :param None
        :param None
        """
        self.tqacc = TqAccount(BOKER_ID, ACCOUNT_ID, PASSWORD)
        self.api = TqApi(account=self.tqacc, auth=TqAuth(
            SDK_USERNAME, SDK_PASSWORD))
        self.account = self.tqacc.get_account()
        logger.info(f"账户权益: {self.account.balance}")
        logger.info(f"可用资金: {self.account.available}")

    @property
    def direction(self):
        """
        获取开仓方向

        :param None
        :return desc: string --> 开仓方向中文描述
        """
        if DIRECTION.upper() == "SELL":
            return "空"
        else:
            return "多"

    def get_old_volume(self):
        """
        获取指定品种已有持仓数量

        :param None
        :return old_volume: int --> 已有持仓数
        """
        if DIRECTION.upper() == "SELL":
            old_volume = self.api.get_position(FUTURE).pos_short
        else:
            old_volume = self.api.get_position(FUTURE).pos_long
        return old_volume

    def get_new_volume(self, old_volume):
        """
        获取指定品种新持仓数量

        :param old_volume: int --> 已有持仓数
        :return new_volume: int --> 新持仓数
        """
        abs_new_volume = old_volume + self.volume_diff_step
        if DIRECTION.upper() == "SELL":
            new_volume = - abs_new_volume
        else:
            new_volume = abs_new_volume
        return new_volume

    def update_target_price(self):
        """
        更新目标价

        :param None
        :return None
        """
        if DIRECTION.upper() == "SELL":
            self.target_price += self.price_diff_step
        else:
            self.target_price -= self.price_diff_step

    def is_target_price(self, price):
        """
        是否达到目标价格

        :param price: float --> 当前价格
        :param bool: boolean --> 是否达到目标价
        """
        if DIRECTION.upper() == "SELL":
            if price >= self.target_price:
                return True
        else:
            if price <= self.target_price:
                return True
        return False

    def is_target_profit(self):
        """
        是否达到目标盈利

        :param None
        :param bool: boolean --> 是否达到目标盈利
        """
        if self.tqacc.get_position(FUTURE).float_profit >= TARGET_PROFIT:
            return True
        else:
            return False

    def is_available_balance(self):
        """
        是否有可用余额

        :param None
        :param bool: boolean --> 是否有可用余额
        """
        if 1 - self.account.available/self.account.balance <= MAX_POSITION_RATIO:
            return True
        else:
            return False

    def log_action(self, action, msg):
        """
        记录交易行为

        :param action: str --> 交易行为
        :param msg: dict --> 消息体字典
        :return None
        """
        send_notification(msg, title=action,
                          category="quant", group="future")
        logger.info(msg)

    def run(self):
        """
        根据K线判断增仓, 减仓及清仓点

        :param None
        :return None
        """
        kline = self.api.get_kline_serial(FUTURE, 86400)  # 获取日内k线
        history_volume = self.get_old_volume()
        target_pos = TargetPosTask(self.api, FUTURE)
        logger.info(
            f"历史持仓 {FUTURE} {self.direction} {history_volume} 手  -->> 盈利 {self.account.float_profit} 元")
        while True:
            self.api.wait_update()
            if self.api.is_changing(kline):
                high = kline.high.iloc[-1]
                low = kline.low.iloc[-1]
                price = kline.close.iloc[-1]
                old_volume = self.get_old_volume()
                logger.info(
                    f"最新价 {price}, 最高价 {high}, 最低价 {low} -->> 当前持仓 {self.direction} {old_volume} 手, 盈利 {self.account.float_profit} 元")

                if self.is_target_profit():
                    target_pos.set_target_volume(0)
                    order_msg = f"已平仓 {FUTURE} {old_volume} 手"
                    self.log_action("平仓成功", order_msg)
                    break

                if self.is_available_balance() and self.is_target_price(price):
                    new_volume = self.get_new_volume(get_new_volume)
                    target_pos.set_target_volume(new_volume)
                    self.update_target_price()
                    order_msg = f"开仓 方向:【{self.direction}】数量: 【{self.volume_diff_step}】价格: 【{price}】"
                    self.log_action("开仓委托", order_msg)


if __name__ == '__main__':
    init_log()
    task = FutureTask()
    task.run()
    task.api.close()
