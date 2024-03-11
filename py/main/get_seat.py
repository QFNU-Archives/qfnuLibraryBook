import asyncio
import logging
import multiprocessing
import os
import random
import signal
import time
import requests
import sys

from telegram import Bot
from get_info import get_date, get_seat_info, get_segment, get_build_id, get_auth_token, encrypt

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

URL_GET_SEAT = "http://libyy.qfnu.edu.cn/api/Seat/confirm"
URL_CHECK_STATUS = "http://libyy.qfnu.edu.cn/api/Member/seat"

# 在代码的顶部定义全局变量
interrupted = False
global_exclude_ids = {7443, 7448, 7453, 7458, 7463, 7468, 7473, 7478, 7483, 7488, 7493, 7498, 7503, 7508, 7513, 7518,
                      7572, 7575, 7578, 7581, 7584, 7587, 7590, 7785, 7788, 7791, 7794, 7797, 7800, 7803, 7806, 7291,
                      7296, 7301, 7306, 7311, 7316, 7321, 7326, 7331, 7336, 7341, 7346, 7351, 7356, 7361, 7366, 7369,
                      7372, 7375, 7378, 7381, 7384, 7387, 7390, 7417, 7420, 7423, 7426, 7429, 7432, 7435, 7438, 7115,
                      7120, 7125, 7130, 7135, 7140, 7145, 7150, 7155, 7160, 7165, 7170, 7175, 7180, 7185, 7190, 7241,
                      7244, 7247, 7250, 7253, 7256, 7259, 7262, 7761, 7764, 7767, 7770, 7773, 7776, 7779, 7782}
seat_result = {}
CHANNEL_ID = "-4163947299"
TELEGRAM_BOT_TOKEN = '6441897020:AAFL9QlApvr64CB440qjehy7zpv5Df3qHqk'
TELEGRAM_URL = "https://telegram.sakurasep.workers.dev/bot"
message = ""
MAX_RETRIES = 3  # 最大重试次数
RETRY_DELAY = 5  # 重试间隔时间(秒)


def send_post_request_and_save_response(url, data, headers):
    retries = 0
    while retries < MAX_RETRIES:
        try:
            response = requests.post(url, json=data, headers=headers, timeout=10)
            response.raise_for_status()
            response_data = response.json()
            return response_data
        except requests.exceptions.Timeout:
            logger.error("请求超时，正在重试...")
            retries += 1
            time.sleep(RETRY_DELAY)
        except Exception as e:
            logger.error(f"request请求异常: {str(e)}")
            retries += 1
            time.sleep(RETRY_DELAY)
    logger.error("超过最大重试次数,请求失败。")
    sys.exit()


def add_message(text):
    global message
    message += text


async def send_seat_result_to_channel():
    try:
        # 使用 API 令牌初始化您的机器人
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        logger.info(f"要发送的消息为： {message}\n")
        await bot.send_message(chat_id=CHANNEL_ID, text=message)
    except Exception as e:
        logger.error(f"发送消息到 Telegram 失败: {e}")


def check_book_status(auth):
    post_data = {
        "page": 1,
        "limit": 3,
        "authorization": auth
    }
    request_headers = {
        "Content-Type": "application/json",
        "Connection": "keep-alive",
        "Accept": "application/json, text/plain, */*",
        "lang": "zh",
        "X-Requested-With": "XMLHttpRequest",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, "
                      "like Gecko)"
                      "Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0",
        "Origin": "http://libyy.qfnu.edu.cn",
        "Referer": "http://libyy.qfnu.edu.cn/h5/index.html",
        "Accept-Encoding": "gzip, deflate",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6,pl;q=0.5",
        "Authorization": auth
    }
    res = send_post_request_and_save_response(URL_CHECK_STATUS, post_data, request_headers)
    # logger.info(res)
    for entry in res["data"]["data"]:
        if entry["statusName"] == "预约成功":
            logger.info("存在已经预约的座位")
            # 发送中断信号停止整个程序
            os.kill(os.getpid(), signal.SIGINT)
            break  # 停止循环


# 状态检测函数
def check_reservation_status(auth_token, seat_id, m):
    global seat_result, interrupted
    check_book_status(auth_token)
    # 状态信息检测
    if 'msg' in seat_result:
        status = seat_result['msg']
        logger.info(status)
        if status == "当前时段存在预约，不可重复预约!":
            logger.info("重复预约, 请检查选择的时间段或是否已经成功预约")
            interrupted = True
        elif status == "预约成功":
            # elif "1" == "1":
            logger.info("成功预约")
            add_message(f"预约状态为:{status}")
            asyncio.run(send_seat_result_to_channel())
            interrupted = True
        elif status == "开放预约时间19:20":
            logger.info("未到预约时间,程序将会 10s 查询一次")
            time.sleep(10)
        elif status == "您尚未登录":
            logger.info("没有登录，请检查是否正确获取了 token")
            interrupted = True
        elif status == "该空间当前状态不可预约":
            logger.info("此位置已被预约")
            if m == "1":
                logger.info(f"{seat_id} 已被预约，加入排除名单")
                global_exclude_ids.add(seat_id)
                time.sleep(1)
                # logger.info(global_exclude_ids)
            elif m == "2":
                seat_id = input("请重新输入想要预约的相同自习室的 id:\n")
                return seat_id
            else:
                logger.info(f"{seat_id} 已被预约，重新刷新状态")
                time.sleep(1)
        else:
            logger.info("未知状态，程序退出")
            interrupted = True
    else:
        logger.error("没有获取到状态信息")


# 预约函数
def post_to_get_seat(select_id, segment, auth):
    # 定义全局变量
    global seat_result
    # 原始数据
    origin_data = '{{"seat_id":"{}","segment":"{}"}}'.format(select_id, segment)
    # logger.info(origin_data)

    # 加密数据
    aes_data = encrypt(str(origin_data))
    # logger.info(aes_data)

    # 测试解密数据
    # aes = decrypt(aes_data)
    # logger.info(aes)

    # 原始的 post_data
    post_data = {
        "aesjson": aes_data,
    }

    request_headers = {
        "Content-Type": "application/json",
        "Connection": "keep-alive",
        "Accept": "application/json, text/plain, */*",
        "lang": "zh",
        "X-Requested-With": "XMLHttpRequest",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, "
                      "like Gecko)"
                      "Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0",
        "Origin": "http://libyy.qfnu.edu.cn",
        "Referer": "http://libyy.qfnu.edu.cn/h5/index.html",
        "Accept-Encoding": "gzip, deflate",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6,pl;q=0.5",
        "Authorization": auth
    }

    # 发送POST请求并获取响应
    seat_result = send_post_request_and_save_response(URL_GET_SEAT, post_data, request_headers)


def prefer_get_select_id(build_id):
    try:
        if build_id == 38:
            logger.info("你选择的是三层的优选模式")
            valid_ranges = list(range(7112, 7152)) + list(range(7192, 7216)) + list(range(7240, 7263))
        elif build_id == 39:
            logger.info("你选择的是四层的优选模式")
            valid_ranges = list(range(7288, 7328)) + list(range(7368, 7392))
        elif build_id == 40:
            logger.info("你选择的是五层的优选模式")
            valid_ranges = list(range(7440, 7480)) + list(range(7520, 7544)) + list(range(7568, 7591))
        else:
            logger.error("不支持的优选位置")
            sys.exit()

        # 从所有有效座位中去除已经被排除的座位
        valid_seats = [seat_id for seat_id in valid_ranges if seat_id not in global_exclude_ids]

        # 随机选择一个座位 id
        if valid_seats:
            select_id = random.choice(valid_seats)
            return select_id
        else:
            logger.warning("没有符合条件的座位可供选择")
            return None
    except KeyboardInterrupt:
        logger.info(f"接收到中断信号，程序将退出。")


# 模式1 && 3
def get_and_select_seat_default(auth, build_id, segment, nowday, m):
    # 初始化
    global message
    try:
        while not interrupted:
            # 优选逻辑
            if m == "1":
                # logger.info(build_id)
                select_id = prefer_get_select_id(build_id)
                logger.info(f"优选的座位是:{select_id}")
                message = f"优选的座位是:{select_id}"
                time.sleep(1)
            # 默认逻辑
            else:
                # logger.info(f"获取的 segment: {segment}")
                data = get_seat_info(build_id, segment, nowday)
                # 检查返回的列表是否为空
                if not data:
                    logger.info("无可用座位")
                    continue
                else:
                    # 随机选择一个字典
                    random_dict = random.choice(data)

                    # 获取该字典中 'id' 键对应的值
                    select_id = random_dict['id']
                    seat_no = random_dict['no']
                    logger.info(f"随机选择的座位为: {select_id} 真实位置: {seat_no}")
                    message = f"随机选择的座位为: {select_id} 真实位置: {seat_no} \n"

            if select_id is None:
                logger.info("选定座位为空, 程序继续运行")
                time.sleep(1)
                continue
            else:
                post_to_get_seat(select_id, segment, auth)
                # logger.info(seat_result)
                check_reservation_status(auth, select_id, m)

    except KeyboardInterrupt:
        logger.info(f"接收到中断信号，程序将退出。")


# 模式2
def get_and_select_seat_selected(auth, segment, seat_id):
    # 初始化
    global seat_result
    try:
        while not interrupted:
            logger.info(f"你选定的座位为: {seat_id}")
            post_to_get_seat(seat_id, segment, auth)
            # logger.info(seat_result)
            check_reservation_status(auth, seat_id, "2")

    except KeyboardInterrupt:
        logger.info(f"接收到中断信号，程序将退出。")


# 进程池
def process_classroom(auth, name, process_num, nowday, m):
    try:
        # 获取基本信息
        build_id = get_build_id(name)
        segment = get_segment(build_id, nowday)
        # 进程池
        with multiprocessing.Pool(processes=process_num) as pool:
            params = [(auth, build_id, segment, nowday, m)] * process_num
            pool.starmap(get_and_select_seat_default, params)
        logger.info("进程完成")
    except KeyboardInterrupt:
        logger.info("收到中断信号，程序将退出")


def default_get_seat(m):
    try:
        # 输入基本信息
        # classroom_names = input("请输入教室名（多个教室名以空格分隔）:\n").split()
        classroom_names = ["西校区图书馆-三层自习室", "西校区图书馆-四层自习室", "西校区图书馆-五层自习室"]
        # process_number = int(input("请输入进程数: \n"))
        process_number = 2
        date = get_date()

        # 获取授权码
        auth_token = get_auth_token()

        processes = []

        for classroom_name in classroom_names:
            p = multiprocessing.Process(target=process_classroom,
                                        args=(auth_token, classroom_name, process_number, date, m))
            processes.append(p)
            p.start()

        for process in processes:
            process.join()
    except KeyboardInterrupt:
        print("主动退出程序，程序将退出。")


def selected_get_seat():
    try:
        # 输入基本信息
        classroom_names = input("请输入教室名: \n").split()
        seat_id = input("请输入预选座位的 id（非真实id）:\n")
        date = get_date()

        # 获取授权码
        auth_token = get_auth_token()

        # 获取基本信息
        for classroom_name in classroom_names:
            build_id = get_build_id(classroom_name)
            segment = get_segment(build_id, date)
            get_and_select_seat_selected(auth_token, segment, seat_id)

    except KeyboardInterrupt:
        print("主动退出程序，程序将退出。")


if __name__ == "__main__":
    try:
        check_book_status(get_auth_token())
        # 三种功能
        # mode = input("请输入选座模式，1:优选模式 2:指定座位 3:默认随机\n")
        mode = "1"
        if mode == "3":
            default_get_seat(mode)
        if mode == "2":
            selected_get_seat()
        if mode == "1":
            default_get_seat(mode)
        else:
            sys.exit()

    except KeyboardInterrupt:
        print("主动退出程序，程序将退出。")
