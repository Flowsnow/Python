#!/usr/bin/env python 
#coding=utf-8
'''
Created on 2016年10月22日上午10:26:18
@author: Flowsnow
@file: /weblogic/user_projects/domains/scripts/diskOverrunHanding.py
@function: 配合定时任务使用，每一个小时监控一次磁盘，磁盘空间超过80%时按照权重自动备份各个节点下的最近最久未使用的日志
'''
#----------------------------import第三方模块----------------------------------
import os
import commands
import time


#------------------------------全局变量声明-------------------------------------
#监控的挂载点目录
monitoredDir='/weblogic'
#域所在目录
domainPath='/weblogic/user_projects/domains'
#磁盘上限，达到此上线的时候就需要调用备份程序，80表示达到磁盘使用率80%
upperNum=80
#备份程序调用后需要将磁盘使用率处理到lowerNum以下，60表示达到磁盘使用率60%
lowerNum=50
#需要处理的log目录,这两种日志的处理策略是备份除了osb.log之外的所有的osblog文件
logDirs=['log','logosb']
#处理掉的日志的备份路径
dstPath='/oradata/log_bak'
#所有的脚本存放目录
scriptsLogPath='/oradata/clg'
#脚本执行的时候产生的日志，用来记录每次操作了那些东西，操作日志存放在dstPath中
logFilename='DiskOverrunHanding.log'


#-------------------------------函数定义--------------------------------------
#command模块获取某个挂载点的使用率,返回值为0-100之间的整数
def getDiskUsage(dir):
    cmd='df '+dir+'''|awk '{if($5=="/weblogic") print $4}'|cut -d '%' -f 1'''
    cmdResult=commands.getstatusoutput(cmd)
    #返回的列表的index=0的值如果为0表示执行成功
    if cmdResult[0]==0:
        return int(cmdResult[1])
    else:
        return -1

#获取某个挂载点的总量，返回值的单位为k
def getDiskSize(dir):
    cmd='df '+dir+'''|awk '{if($5=="/weblogic") print $1}' '''
    cmdResult=commands.getstatusoutput(cmd)
    if cmdResult[0]==0:
        return int(cmdResult[1])
    else:
        return -1
    
#获取dir目录的大小，返回值的单位为k
def getDirSize(dir):
    #cmd='''du -s /weblogic/user_projects/domains/gshx01_domain|awk '{print $1}' '''
    cmd='du -s '+dir+'''|awk '{print $1}' '''
    cmdResult=commands.getstatusoutput(cmd)
    if cmdResult[0]==0:
        return int(cmdResult[1])
    else:
        return -1
    
#获取需要处理的domain，gshx01_domain,gzl02_domain这种后面是两个数字+'_domain'这种形式的。去掉domain    
def getDealDomain():
    initDomains=os.listdir(domainPath)
    dealDomains=[]
    for dom in initDomains:
        if dom[-7:]=='_domain' and dom[-8].isdigit() and dom[-9].isdigit():
            dealDomains.append(dom)
    dealDomains.sort()
    return dealDomains

#获得每个域需要减掉的大小    
def getWeightOfDealDomains(dealDomains):
    #所有domain的大小之和
    allDomainsSize=0
    dealDomainSize=[]
    reducedSizeOfEachDomain=[]
    for domain in dealDomains:
        dir=domainPath+'/'+domain
        domainSize=getDirSize(dir)
        dealDomainSize.append(domainSize)
        allDomainsSize=allDomainsSize+domainSize
    #获取/weblogic的大小
    weblogicSize=getDiskSize(monitoredDir)
    for i in range(len(dealDomains)):
        #公式：当前域减去的大小=当前域的大小*weblogic目录大小*减掉的比例/所有域的大小之和
        sizeD=dealDomainSize[i]*getDiskSize(monitoredDir)*(getDiskUsage(monitoredDir)-lowerNum)/(100*allDomainsSize)
        reducedSizeOfEachDomain.append(sizeD)
    return reducedSizeOfEachDomain
    
#根据domain名称获取server名称
def getServerName(domainName):
    servers=os.listdir(domainPath+'/'+domainName+'/servers')
    serverName=domainName[:-9]
    for server in servers:
        if server[0:server.find('Server_')]==serverName:
            return server
        
#日志保存函数
def saveToLog(st):
    if os.path.exists(scriptsLogPath+'/'+logFilename):
        f=open(scriptsLogPath+'/'+logFilename,'a')
        f.write(st+'\n')	
        f.close()
    else:
        f=open(scriptsLogPath+'/'+logFilename,'w')
        f.write(st+'\n')
        f.close()

def mainDeal():
    dealDomains=getDealDomain()
    reducedSizeOfEachDomain=getWeightOfDealDomains(dealDomains)
    
    #开始处理每一个域下面的日志，直到减掉的日志大小大于当前域的需要减掉的大小
    for i in range(len(dealDomains)):
        reducedSizeOfCurrentDomain=reducedSizeOfEachDomain[i]
        saveToLog(str(i)+' '+str(reducedSizeOfCurrentDomain)+' '+dealDomains[i])
        
        realReducedSize=0
        serverName=getServerName(dealDomains[i])
        
        #开始处理logosb目录，策略：除了osb.log之外mv掉所有的logosb
        logosbPath=domainPath+'/'+dealDomains[i]+'/'+logDirs[1]
        os.chdir(logosbPath)
        logosbFiles=os.listdir(logosbPath)
        for logosbFile in logosbFiles:
            if logosbFile[0:10]=='osb.log.20':
                realReducedSize=realReducedSize+os.path.getsize(logosbFile)
                cmd='mv '+logosbFile+' '+dstPath+'/'+serverName+'_'+logosbFile
                saveToLog(cmd)
                os.system(cmd)
            
        #开始处理log目录
        logPath=domainPath+'/'+dealDomains[i]+'/'+logDirs[0]
        os.chdir(logPath)
        logFiles=os.listdir(logPath)
        logFiles.sort()
        for logFile in logFiles:
            if realReducedSize<=reducedSizeOfCurrentDomain*1024:
                if logFile[0:12]=='grsds.log.20':
                    realReducedSize=realReducedSize+os.path.getsize(logFile)
                    cmd='mv '+logFile+' '+dstPath+'/'+serverName+'_'+logFile
                    saveToLog(cmd)
                    os.system(cmd)
                else:
                    pass
            else:
                break;

def judge():
    saveToLog('')
    logst='时间:'+time.strftime('%Y-%m-%d %H:%M:%S',time.localtime(time.time()))
    saveToLog(logst)
    diskUsage=getDiskUsage(monitoredDir)
    if diskUsage>=upperNum:
        saveToLog('start to deal!')
        mainDeal()
    else:
        saveToLog('nothing to deal!')

if __name__=='__main__':
    judge()
    



