/*
*   Name:控制菜单显示
	Date：2015-06-05
	Author：Kalven
	CopyRight:www.alipiao.com
*/
$.fn.extend({
    //模版添加使用
    LoadWindows: function (userid,iframesrc) {
        WinDialog({
            boxID: "webdialogAdd",
            title: "手工代购车票窗口",
            showborder: true,
			boxzool:true, 
            lock: false, //是否限制拖动范围；
            drag: true,
            fixed: true, //拖动滚动条窗口不跟屏
            showbg:true,//设置背景
            width: 580,
            height: 420,
            content:"iframe:http://www.baidu.com"
        })
    }
})