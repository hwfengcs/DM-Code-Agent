def chunk_text(text, max_chunk_size=300):
    """
    将文本切分成固定大小的块，保持段落和表格的完整性。
    
    Args:
        text (str): 需要切分的文本
        max_chunk_size (int): 每个块的最大大小，默认为300
        
    Returns:
        list: 包含切分后文本块的列表
    """
    # 按行分割文本
    lines = text.split('\n')
    
    chunks = []
    current_chunk = []
    current_size = 0
    in_table = False
    table_content = []
    
    for line in lines:
        # 检测表格开始 (含有 | 字符的行，通常是表格)
        if '|' in line and not in_table:
            # 可能是表格的开始
            in_table = True
            
            # 保存当前块
            if current_chunk:
                chunks.append('\n'.join(current_chunk))
                current_chunk = []
                current_size = 0
            
            table_content.append(line)
        
        # 表格内容
        elif in_table:
            table_content.append(line)
            
            # 如果遇到空行，可能表示表格结束
            if not line.strip():
                in_table = False
                chunks.append('\n'.join(table_content))
                table_content = []
            
        # 普通内容
        else:
            line_length = len(line)
            
            # 如果加上这一行会超过最大块大小，并且当前块不为空，则保存当前块
            if current_size + line_length > max_chunk_size and current_chunk:
                chunks.append('\n'.join(current_chunk))
                current_chunk = []
                current_size = 0
            
            # 添加新行到当前块
            current_chunk.append(line)
            current_size += line_length
            
            # 如果当前行为空，可能是段落结束
            # 检查当前块大小，如果已经足够大，则保存当前块
            if not line.strip() and current_size > max_chunk_size // 2:
                chunks.append('\n'.join(current_chunk))
                current_chunk = []
                current_size = 0
    
    # 处理剩余的表格内容
    if in_table and table_content:
        chunks.append('\n'.join(table_content))
    
    # 处理最后剩余的块
    if current_chunk:
        chunks.append('\n'.join(current_chunk))
    
    return chunks