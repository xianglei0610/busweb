# -*- coding:utf-8 -*-


class Manager(object):
    def get(self):
        """
        获取一个有效的账号
        """
        return None

    def get_and_lock(self):
        pass

    def all(self):
        """
        所有有效的账号
        """
        return []

    def valid(self, rebot):
        """
        验证此账号是否有效
        """
        return True

    def login(self):
        """
        登陆
        """
        pass

    def lock(self, rebot):
        """
        锁住账号，使之不被使用
        """
        pass

    def free(self, rebot):
        """
        释放锁
        """
        pass


class ApiScqcpManager(Manager):
    pass


class WebScqcpManager(Manager):
    pass
