import re
import json
from openai import OpenAI
import os

def middle_json_model(prompt):

    client = OpenAI(
        # 若没有配置环境变量，请用百炼API Key将下行替换为：api_key="sk-xxx",
        api_key=os.getenv("DASHSCOPE_API_KEY"), 
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    completion = client.chat.completions.create(
        model="qwen-plus", # 此处以qwen-plus为例，可按需更换模型名称。模型列表：https://help.aliyun.com/zh/model-studio/getting-started/models
        messages=[
            {'role': 'system', 'content': 'You are a helpful assistant.'},
            {'role': 'user', 'content': prompt}],
        response_format={"type": "json_object"}
        )
        
    return completion.choices[0].message.content





def reflection(user_query,action, memory_global):
    prompt='''
    你是一个专业的任务规划助手。现在原计划遇到了一些困难：
1. 分析用户的查询:{0}
2. 反复重试了三次的action:{1}

##目前已有的信息:
{2}


## 可用工具
1. **本地文档搜索**：搜索本地星辰电动ES9的文档，包含以下章节：
   - 产品概述
   - 设计理念
   - 技术规格
   - 驱动系统
   - 电池与充电
   - 智能座舱
   - 智能驾驶
   - 安全系统
   - 车身结构
   - 舒适性与便利性
   - 版本与配置
   - 价格与购买信息
   - 售后服务
   - 环保贡献
   - 用户评价
   - 竞品对比
   - 常见问题
   - 联系方式

2. **网络搜索**：在互联网上搜索相关信息

## 工具选择规则
- 当查询明确涉及星辰电动ES9的具体信息、参数、功能或服务时，优先使用**本地文档搜索**
- 当查询涉及以下情况时，使用**网络搜索**：
  - 与其他品牌车型的详细对比
  - 最新市场动态或新闻
  - 非官方的用户体验或评测
  - 星辰电动ES9文档中可能没有的信息
  - 需要实时数据（如当前市场价格波动等）

## prompt延伸的规则
- 本地检索的查询扩展侧重于产品信息的深度查询
- 网络检索的查询扩展侧重于本地无法检索到的信息

###重要！
至多再扩展不超过3个查询，如果需要扩展则按照下面的输出格式输出，如果不需要则返回None




## 输出格式
你的输出应该是一个JSON格式的列表，每个项目包含：
1. `action_name`：工具名称（"本地文档搜索"或"网络搜索"）
2. `prompts`：一个扩展的问题，如果是网络检索，prompt不包含电动ES9，如果是本地检索，prompt只包含询问电动ES9，检索内容一定是一个简单问题，不包含对比
[
  {{
    "action_name": "工具名称",
    "prompts":'查询内容'
  }}
  ...
]

    '''.format(user_query,memory_global)
    result=(middle_json_model(prompt))
    # print(result)
    json_list=extract_json_content(result)
    try:
        structure_output=json.loads(json_list)
    except:
        structure_output = None

    return structure_output


def extract_json_content(input_str):
    """
    提取字符串中第一个"["和最后一个"]"之间的内容（包括中括号）
    
    Args:
        input_str (str): 需要处理的输入字符串
    
    Returns:
        str or None: 提取的JSON内容，如果没有匹配则返回None
    """
    # 使用正则表达式匹配第一个"["到最后一个"]"之间的内容
    # [\s\S]* 匹配任意字符（包括换行符）
    pattern = r'(\[[\s\S]*\])'
    match = re.search(pattern, input_str)
    
    # 如果匹配成功，返回匹配的内容；否则返回None
    return match.group(1) if match else None