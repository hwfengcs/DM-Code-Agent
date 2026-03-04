from dotenv import load_dotenv
import os
import http.client
import json

def serper_search(q="apple inc", hl="zh-cn",num = 20):
    """
    使用 Serper API 进行常规搜索的函数

    参数:
        q (str): 搜索关键词，默认为 "apple inc"
        hl (str): 语言，默认为 "zh-cn"（中文）

    返回:
        dict: 搜索结果的 JSON 数据
    """
    return make_request(q, hl, "/search", num)

def serper_images(q="apple inc", hl="zh-cn"):
    """
    使用 Serper API 进行图片搜索的异步函数

    参数:
        q (str): 搜索关键词，默认为 "apple inc"
        hl (str): 语言，默认为 "zh-cn"（中文）

    返回:
        dict: 图片搜索结果的 JSON 数据
    """
    return make_request(q, hl, "/images")

def serper_videos(q="apple inc", hl="zh-cn"):
    """
    使用 Serper API 进行视频搜索的异步函数

    参数:
        q (str): 搜索关键词，默认为 "apple inc"
        hl (str): 语言，默认为 "zh-cn"（中文）

    返回:
        dict: 视频搜索结果的 JSON 数据
    """
    return make_request(q, hl, "/videos")

def make_request(q, hl, endpoint, num=10):
    """
    发送请求到 Serper API 的通用函数

    参数:
        q (str): 搜索关键词
        hl (str): 语言
        endpoint (str): API 的 endpoint

    返回:
        dict: 搜索结果的 JSON 数据
    """
    # 加载.env文件
    load_dotenv()

    api_key = os.getenv("SERPER_API_KEY")

    conn = http.client.HTTPSConnection("google.serper.dev")
    payload = json.dumps({
        "q": q,
        "hl": hl,
        "num": num
    })
    headers = {
        'X-API-KEY': api_key,
        'Content-Type': 'application/json'
    }
    conn.request("POST", endpoint, payload, headers)
    res = conn.getresponse()
    data = res.read()
    return json.loads(data.decode("utf-8"))


def process_search_results(search_results):
    """
    处理 search 查询的返回值，返回两个列表，第一个是 snippet，第二个是 question。

    参数:
        search_results (dict): search 查询的返回值，是一个 JSON 格式的字典。

    返回:
        tuple: 一个包含两个列表的元组，第一个列表是 snippet，第二个列表是 question。
    """
    snippets = []
    questions = []

    # 处理 organic 搜索结果，提取 snippet
    if 'organic' in search_results:
        for result in search_results['organic']:
            message = {
                "title": result['title'],
                "url": result['link'],
                "content": result['snippet']
            }
            snippets.append(message)


    # 处理相关问题，提取 question
    if 'peopleAlsoAsk' in search_results:
        for question_data in search_results['peopleAlsoAsk']:
            if 'question' in question_data:
                questions.append(question_data['question'])

    return snippets, questions

if __name__=='__main__':
    # 假设 search_results 是 search 函数的返回值
    search_results = serper_search(q="人工智能", hl="zh-cn")
    snippets, questions = process_search_results(search_results)
    
    # 打印 snippet 列表
    print("Snippets:")
    for snippet in snippets:
        print(snippet)
    
    # 打印 question 列表
    print("\nQuestions:")
    for question in questions:
        print(question)