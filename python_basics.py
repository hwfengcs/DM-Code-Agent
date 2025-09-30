# Python 初学者基本语法示例

# 1. 变量和数据类型
# 整数
age = 25
# 浮点数
height = 1.75
# 字符串
name = "Alice"
# 布尔值
is_student = True
# 列表
fruits = ["apple", "banana", "orange"]
# 字典
person = {"name": "Bob", "age": 30}

print("变量和数据类型:")
print(f"姓名: {name}, 年龄: {age}, 身高: {height}")
print(f"水果列表: {fruits}")
print(f"人员信息: {person}")
print()

# 2. 基本运算
print("基本运算:")
a = 10
b = 3
print(f"加法: {a} + {b} = {a + b}")
print(f"减法: {a} - {b} = {a - b}")
print(f"乘法: {a} * {b} = {a * b}")
print(f"除法: {a} / {b} = {a / b}")
print(f"取余: {a} % {b} = {a % b}")
print(f"幂运算: {a} ** {b} = {a ** b}")
print()

# 3. 控制结构
print("控制结构:")
# if-else 语句
score = 85
if score >= 90:
    print("优秀")
elif score >= 80:
    print("良好")
elif score >= 70:
    print("中等")
else:
    print("需要努力")

# for 循环
print("\nfor 循环:")
for i in range(5):
    print(f"循环次数: {i}")

for fruit in fruits:
    print(f"水果: {fruit}")

# while 循环
print("\nwhile 循环:")
count = 0
while count < 3:
    print(f"计数: {count}")
    count += 1
print()

# 4. 函数
print("函数:")
def greet(name):
    """简单的问候函数"""
    return f"Hello, {name}!"

def add_numbers(a, b):
    """加法函数"""
    return a + b

print(greet("World"))
print(f"5 + 3 = {add_numbers(5, 3)}")
print()

# 5. 类
print("类:")
class Dog:
    def __init__(self, name, breed):
        self.name = name
        self.breed = breed
    
    def bark(self):
        return f"{self.name} says: Woof!"
    
    def info(self):
        return f"这是一只{self.breed}犬，名叫{self.name}"

# 创建对象
my_dog = Dog("Buddy", "金毛")
print(my_dog.bark())
print(my_dog.info())
print()

# 6. 异常处理
print("异常处理:")
try:
    result = 10 / 0
except ZeroDivisionError:
    print("错误：不能除以零！")
else:
    print(f"结果是: {result}")
finally:
    print("异常处理完成")

print("\nPython基础语法示例结束！")