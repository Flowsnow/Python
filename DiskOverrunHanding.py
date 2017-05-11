#!/usr/bin/env python
# coding=utf-8
"""
Created on 2016年10月22日上午10:26:18
@author: Flowsnow
@file: /weblogic/user_projects/domains/scripts/diskOverrunHanding.py
@function: 配合定时任务使用，每一个小时监控一次磁盘，磁盘空间超过80%时按照权重自动备份各个节点下的最近最久未使用的日志
@usage: */10 * * * * python /weblogic/user_projects/domains/scripts/DiskOverrunHanding.py
"""
# ----------------------------import第三方模块----------------------------------
import os
import commands
import time


# ------------------------------全局变量声明-------------------------------------
# 监控的挂载点目录，用于判断磁盘是否达到报警线
monitoredDir = '/weblogic'
# 域所在目录
domainPath = '/weblogic/user_projects/domains'
# 磁盘上限，达到此上线的时候就需要调用备份程序，80表示达到磁盘使用率80%
upperNum = 80
# 备份程序调用后需要将磁盘使用率处理到lowerNum以下，60表示达到磁盘使用率60%
lowerNum = 60
# 需要处理的log目录
logDirs = ['log/gshx', 'log/gswf']
# 处理掉的日志的备份路径
dstPath = '/oradata/log_bak'
# 所有的脚本存放目录
scriptsLogPath = '/oradata/clg'
# 脚本执行的时候产生的日志，用来记录每次操作了那些东西，操作日志存放在dstPath中
logFilename = 'DiskOverrunHanding.log'


# -------------------------------函数定义--------------------------------------
# command模块获取某个挂载点的使用率,返回值为0-100之间的整数
def get_disk_usage(d):
    cmd = 'df ' + d + '''|awk '{if($5 ==  "/weblogic") print $4}'|cut -d '%' -f 1'''
    cmd_result = commands.getstatusoutput(cmd)
    # 返回的列表的index=0的值如果为0表示执行成功
    if cmd_result[0] == 0:
        return int(cmd_result[1])
    else:
        return -1


# 获取某个挂载点的总量，返回值的单位为k
def get_disk_size(d):
    cmd = 'df ' + d + '''|awk '{if($5=="/weblogic") print $1}' '''
    cmd_result = commands.getstatusoutput(cmd)
    if cmd_result[0] == 0:
        return int(cmd_result[1])
    else:
        return -1


# 获取dir目录的大小，返回值的单位为k
def get_dir_size(d):
    # cmd = '''du -s /weblogic/user_projects/domains/gshx01_domain|awk '{print $1}' '''
    cmd = 'du -s ' + d + '''|awk '{print $1}' '''
    cmd_result = commands.getstatusoutput(cmd)
    if cmd_result[0] == 0:
        return int(cmd_result[1])
    else:
        return -1


# 获取需要处理的domain，gshx01_domain,gzl02_domain这种后面是两个数字+'_domain'这种形式的。去掉domain
def get_deal_domain():
    init_domains = os.listdir(domainPath)
    deal_domains = []
    for dom in init_domains:
        if dom[-7:] == '_domain' and dom[-8].isdigit() and dom[-9].isdigit():
            deal_domains.append(dom)
    deal_domains.sort()
    return deal_domains


# 获得每个域需要减掉的大小
def get_weight_of_deal_domains(deal_domains):
    # 所有domain的大小之和
    all_domains_size = 0
    deal_domain_size = []
    reduced_size_of_each_domain = []
    for domain in deal_domains:
        d = domainPath + '/' + domain
        domain_size = get_dir_size(d)
        deal_domain_size.append(domain_size)
        all_domains_size = all_domains_size + domain_size
    for i in range(len(deal_domains)):
        # 公式：当前域减去的大小=当前域的大小*weblogic目录大小*减掉的比例/所有域的大小之和
        size_d = deal_domain_size[i] * get_disk_size(monitoredDir) * (get_disk_usage(monitoredDir) - lowerNum) / (100 * all_domains_size)
        reduced_size_of_each_domain.append(size_d)
    return reduced_size_of_each_domain


# 日志保存函数
def save_to_log(st):
    if os.path.exists(scriptsLogPath + '/' + logFilename):
        f = open(scriptsLogPath + '/' + logFilename, 'a')
        f.write(st + '\n')
        f.close()
    else:
        f = open(scriptsLogPath + '/' + logFilename, 'w')
        f.write(st + '\n')
        f.close()

# 日志文件的创建时间排序的比较函数
def compare(x, y):
    stat_x = os.stat(x)
    stat_y = os.stat(y)
    if stat_x.st_ctime <= stat_y.st_ctime:
        return -1
    else:
        return 1

def main_deal():
    deal_domains = get_deal_domain()
    reduced_size_of_each_domain = get_weight_of_deal_domains(deal_domains)

    # 开始处理每一个域下面的日志，直到减掉的日志大小大于当前域的需要减掉的大小
    for i in range(len(deal_domains)):
        reduced_size_of_current_domain = reduced_size_of_each_domain[i]
        save_to_log(str(i) + ' ' + str(reduced_size_of_current_domain) + ' ' + deal_domains[i])
        real_reduced_size = 0
        for logDir in logDirs:
            log_path = domainPath + '/' + deal_domains[i] + '/' + logDir
            if not os.path.exists(log_path):
                continue
            save_to_log(log_path)
            os.chdir(log_path)
            log_files = os.listdir(log_path)
            log_files.sort(compare)
            for log_file in log_files:
                if real_reduced_size <= reduced_size_of_current_domain * 1024:
                    if log_file[-4:] != '.log':
                        real_reduced_size = real_reduced_size + os.path.getsize(log_file)
                        cmd = 'mv ' + log_file + ' ' + dstPath + '/' + log_file
                        save_to_log(cmd)
                        os.system(cmd)
                    else:
                        pass
                else:
                    break
            else:
                if real_reduced_size <= reduced_size_of_current_domain * 1024:
                    save_to_log('当前域已经没有可以备份的日志')
                else:
                    pass


def judge():
    save_to_log('')
    log_st = '时间:' + time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))
    save_to_log(log_st)
    disk_usage = get_disk_usage(monitoredDir)
    if disk_usage >= upperNum:
        save_to_log('start to deal!')
        main_deal()
    else:
        save_to_log('nothing to deal!')

if __name__ == '__main__':
    judge()
