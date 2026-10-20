# 已提交响应的header/body EOF补充

v2-eof整文件实际335pass/1error（16m01s），reconciliation remote_child_commit_lost_response测试体与replacement ACKED/state断言通过；teardown的ssl.SSLEOFError发生于end_headers→flush_headers→wfile.write(headers)，仍属于SIGKILL后响应写入，而非业务处理异常。

授权把同一成功响应的send_response/send_header/end_headers/wfile.write(raw)整个**事务完成后的输出区**纳入仅ssl.SSLEOFError处理。请求读取、解析、验签、SM2、事务、状态判断及其它handler_error路径不变；不吞通用SSLError、证书错误或业务异常。不再人为按header/body的一条wfile调用拆开同一响应阶段，避免遗漏相同断链语义。旧335pass/1error原件与v2/更早错误均保留。v3整文件与后续普通PG仍需完整实际验证，生产逻辑不改。
