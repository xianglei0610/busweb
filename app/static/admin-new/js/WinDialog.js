/*
*   Name:弹出层
	Date：2013-05-06
	Author：Kalven
	CopyRight:www.12308.com
*/
; (function ($) {
    Array.prototype.min = function () { //最小值
        return Math.min.apply({},
		this);
    };
    Array.prototype.max = function () {
        return Math.max.apply({}, this);
    };
    Array.prototype.indexOf = function (val) {
        for (var i = 0; i < this.length; i++) {
            if (this[i] == val) return i;
        };
        return -1;
    };
    Array.prototype.remove = function (val) {
        var index = this.indexOf(val);
        if (index > -1) {
            this.splice(index, 1);
        };
    };
    WinDialog = function (o) {
        defaults = $.extend({
            type: "dialog",//弹窗类型
            theme: "defaults",//主题
            title: "",//窗口标题文字;
            boxID: new Date().getTime(),//弹出层ID;
            referID: "", //相对于这个ID的位置进行定位
            content: "text:内容",//内容(可选内容为){ text | img | grally | swf | url | iframe};
            width: "",//窗口宽度;
            height: "",//窗口高度;
            time: "",//自动关闭等待时间;(单位秒);
            drag: false,//是否启用拖动( 默认为不开启);
            lock: true, //是否限制拖动范围；
            fixed: false,//是否开启固定定位;
            showbg: false,//是否显示遮罩层( 默认为false);
            showborder: false, //是否显示边框
            showtitle: true,//是否显示弹出层标题( 默认为显示);
            boxzool: false,  //是否设置窗口放大与缩小
            position: "",//设定弹出层位置,默认居中;
            arrow: "left",//箭头方向
            tips: { val: 10, style: "red", auto: false },//提示层设置（val => 箭头偏移量 | style => 提示层风格 | auto => 提示层位置自适应）
            yesBtn: null, //弹窗判断是否yes
            noBtn: null,  //弹窗判断是否no
            closestyle: "1",//关闭窗口类型效果
            closeCallback: "",//弹出窗关闭后执行的函数;
            openCallback: ""//弹出窗打开后执行的函数;
        }, o);
        WinDialog.init(defaults);
    };

    $.extend(WinDialog, {
        data: {
            _this: null,
            winarr:[],
            zindex: 2015515
        },
        init: function (o) {
            if (WinDialog.getID(o.boxID)) return;
            WinDialog.create(o);
            WinDialog.loadContent(o);
            WinDialog.valmin(o);
            WinDialog.valmax(o);
            WinDialog.restore(o);
            if (o.yesBtn) WinDialog.yesBtn(o);
            if (o.noBtn) WinDialog.noBtn(o);
            if (o.fixed) { WinDialog.webfixed(o.boxID); WinDialog.webfixed(o.boxID + "_move_temp"); }
            if (typeof o.time === "number") {
                setTimeout(function () {
                    WinDialog.webclose(o.boxID, o.closeCallback, o.closestyle);
                }, o.time);
            };
             if (!WinDialog.browser.isIE) {
                 $(window).resize(function () {
                     WinDialog.setXY(o.boxID, o.position, o.referID, o.fixed);
                 });
             };
            $(".ui_btn_close", _this).on("click", function () {
                WinDialog.webclose(o.boxID, o.closeCallback, o.closestyle);
                return false;
            });
            var winarr = WinDialog.data.winarr;
            _this.on("mousedown", function () {
                this.style.zIndex = WinDialog.data.zindex += 1;
                for (var i = 0; i < winarr.length; i++) {
                    if (winarr[i][0] == o.boxID) winarr[i][1] = this.style.zIndex;
                };
            });
            document.onkeydown = function (e) {
                e = e || window.event;
                if (e.keyCode == 27) {
                    var zindex = [];
                    for (var i = 0; i < winarr.length; i++) {
                        zindex.push(winarr[i][1]);
                    };
                    for (var j = 0; j < zindex.length; j++) {
                        if (winarr[j][1] == zindex.max()) {
                            WinDialog.webclose(winarr[j][0], o.closeCallback, o.closestyle);
                            zindex.remove(zindex.max());
                            winarr.remove(winarr[j]);
                        };
                    };
                };
            };
        },
        getTag: function (tag) {
            return document.getElementsByTagName(tag);
        },
        loadJS: function () {
            //path, ocall, ecall, chartset,hasJS;参数
            var fileName = arguments[0];
            var ocall = arguments[1];
            var ecall = arguments[2];
            var chartset = arguments[3];
            var hasJS = false || arguments[4]; //是否保留JS--为真不删除，假移除				
            var objId = WinDialog.getID(fileName.replace(".js", "js"));
            if (WinDialog.type(objId) != "null") { return; }//如果存在则返回						
            chartset = chartset || 'utf-8';
            var script = document.createElement("script");
            script.charset = chartset;
            script.type = "text/javascript";
            script.id = fileName.replace(".js", "js");
            script.src = "js/" + fileName + "?" + new Date().getTime();
            var head = WinDialog.getTag('HEAD').item(0);
            if (WinDialog.browser.isIE) {
                script.onreadystatechange = function () {
                    if (!(/loaded|complete/i.test(script.readyState))) return;
                    if ('function' == typeof ocall) ocall();
                    if (hasJS == true) return;
                    script.onreadystatechange = null;
                    script.parentNode.removeChild(script);
                    script = null
                }
            } else {
                script.onload = function () {
                    if ('function' == typeof ocall) ocall();
                    if (hasJS == true) return;
                    script.parentNode.removeChild(script);
                    script = null
                }
            }
            if ('function' == typeof ecall)
                script.onerror = function () {
                    if ('function' == typeof ecall) ecall();
                    if (hasJS == true) return;
                    script.parentNode.removeChild(script);
                    script = null
                };
            head.appendChild(script);
        },
        getID: function (id) { return document.getElementById(id); },
        browser: function () {
            var a = navigator.userAgent.toLowerCase();
            var b = {};
            b.isStrict = document.compatMode == "CSS1Compat";
            b.isFirefox = a.indexOf("firefox") > -1;
            b.isOpera = a.indexOf("opera") > -1;
            b.isSafari = (/webkit|khtml/).test(a);
            b.isSafari3 = b.isSafari && a.indexOf("webkit/5") != -1;
            b.isIE = !b.isOpera && a.indexOf("msie") > -1;
            b.isIE6 = !b.isOpera && a.indexOf("msie 6") > -1;
            b.isIE7 = !b.isOpera && a.indexOf("msie 7") > -1;
            b.isIE8 = !b.isOpera && a.indexOf("msie 8") > -1;
            b.isGecko = !b.isSafari && a.indexOf("gecko") > -1;
            b.isMozilla = document.all != undefined && document.getElementById != undefined && !window.opera != undefined;
            return b
        }(),
        pageSizeGet: function () {
            var a = WinDialog.browser.isStrict ? document.documentElement : document.body;
            var b = ["clientWidth", "clientHeight", "scrollWidth", "scrollHeight"];
            var c = {};
            for (var d in b) c[b[d]] = a[b[d]];
            c.scrollLeft = document.body.scrollLeft || document.documentElement.scrollLeft;
            c.scrollTop = document.body.scrollTop || document.documentElement.scrollTop;
            return c
        },
        getPosition: function (obj) {
            if (typeof (obj) == "string") obj = WinDialog.getID(obj);
            var c = 0;
            var d = 0;
            var w = obj.offsetWidth;
            var h = obj.offsetHeight;
            do {
                d += obj.offsetTop || 0;
                c += obj.offsetLeft || 0;
                obj = obj.offsetParent
            } while (obj) return {
                x: c,
                y: d,
                width: w,
                height: h
            }
        },
        safeRange: function (obj) {
            var b = WinDialog.getID(obj);
            var c, d, e, f, g, h, j, k;
            j = b.offsetWidth;
            k = b.offsetHeight;
            p = WinDialog.pageSizeGet();
            c = 0;
            e = p.clientWidth - j;
            g = e / 2;
            d = 0;
            f = p.clientHeight - k;
            var hc = p.clientHeight * 0.382 - k / 2;
            h = (k < p.clientHeight / 2) ? hc : f / 2;
            if (g < 0) g = 0;
            if (h < 0) h = 0;
            return {
                width: j,
                height: k,
                minX: c,
                minY: d,
                maxX: e,
                maxY: f,
                centerX: g,
                centerY: h
            };
        },
        hasClass: function (ele, cls) {
            return ele.className.match(new RegExp('(\\s|^)' + cls + '(\\s|$)'));
        },
        addClass: function (ele, cls) {
            if (!WinDialog.hasClass(ele, cls)) ele.className += " " + cls;
        },
        addCSS: function (val) {
            var b = this.style;
            if (!b) {
                b = this.style = document.createElement('style');
                b.setAttribute('type', 'text/css');
                document.getElementsByTagName('head')[0].appendChild(b);
            };
            b.styleSheet && (b.styleSheet.cssText += val) || b.appendChild(document.createTextNode(val));
        },
        getStyle: function (element) {
            return element.currentStyle || document.defaultView.getComputedStyle(element, null);
        },
        getTag: function (tag) {
            return document.getElementsByTagName(tag);
        },
        type: function (obj) {
            if (obj == null) {
                return String(obj);
            }
            return typeof obj === "object" || typeof obj === "function" ? "object" : typeof obj;
        },
        webfixed: function (obj) {
            var o = WinDialog.getID(obj);
            if (!WinDialog.browser.isIE6) {
                o.style.position = "fixed";
            } else {
                var getClassName = function (ele, name) {
                    var ele = WinDialog.getTag(ele);
                    var arr = [];
                    for (var i = 0; i < ele.length; i++) {
                        if (ele[i].className == name) {
                            arr.push(ele[i]);
                        }
                    }
                    return arr;
                };
                var d = getClassName("div", "ui_dialog_fixed");
                if (WinDialog.getStyle(WinDialog.getID("page"))["backgroundImage"] != "none") {
                    WinDialog.addCSS(".ui_dialog_fixed{width:100%; height:1px; position:absolute; z-index: 891201; left:expression(documentElement.scrollLeft+documentElement.clientWidth-this.offsetWidth); top:expression(documentElement.scrollTop)}.body-fixed{background-attachment:fixed;}");
                } else {
                    WinDialog.addCSS(".ui_dialog_fixed{width:100%; height:1px; position:absolute; z-index: 891201; left:expression(documentElement.scrollLeft+documentElement.clientWidth-this.offsetWidth); top:expression(documentElement.scrollTop)}.body-fixed{background-attachment:fixed;background-image:url(about:blank);}");
                };
                if (d.length == 0) {
                    var wrap = document.createElement("div");
                    wrap.className = 'ui_dialog_fixed';
                    wrap.appendChild(o);
                    document.body.appendChild(wrap);
                    WinDialog.addClass(WinDialog.getTag("html")[0], "body-fixed");
                } else {
                    d[0].appendChild(o);
                }
            }
        },
        setXY: function (obj, position, referID, fixed) {
            var p = WinDialog.pageSizeGet(),
			o = WinDialog.safeRange(obj),
			D = WinDialog.getID(obj);
            if (referID) {
                s = WinDialog.safeRange(referID);
                rp = WinDialog.getPosition(referID);
            }
            var _this = position,
			st = fixed === true ? 0 : p.scrollTop;
            if (referID != undefined && referID != "") {
                var left = !_this.right ? parseInt(_this.left) : p.clientWidth - s.width - parseInt(_this.right);
                var top = !_this.bottom ? parseInt(_this.top) : p.clientHeight - s.height - parseInt(_this.bottom);
                left1 = rp.x + parseInt(_this.left); //inside
                left2 = rp.x + parseInt(_this.left) + s.width; //outside
                right1 = rp.x + s.width - o.width - parseInt(_this.right); //inside
                right2 = rp.x - o.width - parseInt(_this.right); //outside
                top1 = rp.y + parseInt(_this.top); //inside
                top2 = rp.y + parseInt(_this.top) + s.height; //outside
                bottom1 = rp.y + s.height - o.height - parseInt(_this.bottom); //inside
                bottom2 = rp.y - o.height - parseInt(_this.bottom); //outside
                left = !_this.right ? (_this.lin ? left1 : left2) : (_this.rin ? right1 : right2);
                top = !_this.bottom ? (_this.tin ? top1 : top2) : (_this.bin ? bottom1 : bottom2);
                D.style.left = left + "px";
                D.style.top = top + "px";
            } else {
                if (!_this.left && !_this.right) {
                    D.style.left = o.centerX + "px";
                } else {
                    if (!_this.right) {
                        D.style.left = parseInt(_this.left) + "px";
                    } else {
                        D.style.right = parseInt(_this.right) + "px";
                    };
                };
                if (!_this.top && !_this.bottom) {
                    D.style.top = o.centerY + st + "px";
                } else {
                    if (!_this.bottom) {
                        D.style.top = parseInt(_this.top) + st + "px";
                    } else {
                        D.style.top = p.clientHeight - D.offsetHeight - parseInt(_this.bottom) + "px";
                    }
                }
            }
        },
        create: function (o) {
            var boxDom = "<div class=\"ui_dialog_wrap\"><div id=\"" + o.boxID + "\" class=\"ui_dialog\">";
            boxDom += "<table class=\"ui_table_wrap\" cellspacing=\"0\" cellpadding=\"0\" border=\"0\"><tbody>";
            boxDom += "<tr><td class=\"ui_border ui_td_00\"></td><td class=\"ui_border ui_td_01\"></td><td class=\"ui_border ui_td_02\"></td></tr>";
            boxDom += "<tr><td class=\"ui_border ui_td_10\"></td><td class=\"ui_td_11\"><table class=\"ui_dialog_main\" cellspacing=\"0\" cellpadding=\"0\" border=\"0\"><tbody>";
            boxDom += "<tr><td class=\"td_overried\"><div class=\"ui_title_wrap\"><div class=\"ui_title\"><div class=\"ui_title_text\"><span class=\"ui_title_icon\"></span>" + o.title + "</div><div class=\"ui_btn_wrap\"><a class=\"ui_btn_close\">×</a><a class=\"ui_btn_restore\">还原</a><a class=\"ui_btn_max\">最大化</a><a class=\"ui_btn_min\">最小化</a></div></div></div></td></tr>";
            boxDom += "<tr><td><div class=\"ui_content\" id=\"" + o.boxID + "_content\"></div></td></tr>";
            boxDom += "<tr><td><div class=\"ui_button_wrap\"><div class=\"ui_resize\"></div></div></td></tr></tbody></table>";
            boxDom += "</td><td class=\"ui_border ui_td_12\"></td></tr>";
            boxDom += "<tr><td class=\"ui_border ui_td_20\"></td><td class=\"ui_border ui_td_21\"></td><td class=\"ui_border ui_td_22\"></td></tr></tbody></table>";
            boxDom += "<iframe src=\"about:blank\" class=\"ui_iframe\" style=\"position:absolute;left:0;top:0; filter:alpha(opacity=0);opacity:0; scrolling=no;border:none;z-index:10714;\"></iframe>";
            boxDom += "</div><div class=\"ui_move_temp\" id=\"" + o.boxID + "_move_temp\"></div><div class=\"ui_overlay\"><iframe src=\"about:blank\" style=\"width:100%;height:" + $(document).height() + "px;filter:alpha(opacity=50);opacity:0.5;scrolling=no;border:none;z-index:870611;\"></iframe></div></div>";
            $(boxDom).appendTo("body"); //添加至面页底部
            _this = $("#" + o.boxID);
            _this.css("zIndex", WinDialog.data.zindex += 1).addClass("ui_dialog_restore").parent().addClass("ui_dialog_theme_" + o.theme);
            if (o.type == "tips") o.showtitle = false;
            if (o.showtitle != true) {
                $(".ui_title_wrap", _this).remove();
            };
            if (o.boxzool != true) //默认最大小，最小化，恢复都不显示
            {
                $(".ui_btn_restore", _this).remove();
                $(".ui_btn_max", _this).remove();
                $(".ui_btn_min", _this).remove();
            }
            //是否显示背景画布块
            if (o.showbg) {
                _this.parent().find(".ui_overlay").css("visibility", "visible");
            };
            //设置显示弹窗边框(false不显示)
            if (!o.showborder) {
                _this.find(".ui_border").css({
                    width: "0px", height: "0px", fontSize: "0", lineHeight: "0", visibility: "hidden", overflow: "hidden"
                });
                //使用最小化/与最大化窗口时控制窗口边距
                _this.find(".ui_resize").css({
                    right: "5px", bottom: "5px"
                });
                if (o.type == "dialog") _this.find(".ui_dialog_main").addClass("ui_box_shadow");
            };
            WinDialog.setPosition(o);
            //增加控制屏目调整
           // $(window).bind("scroll resize", function () {WinDialog.setPosition(o);});
        },
        loadContent: function (o) {
            var $contentID = $(".ui_content", _this), winarr = WinDialog.data.winarr;
            var tipsDom = "<em class=\"ui_arrow arrow-" + o.arrow + "\" style=\"z-index:1;\"></em><span class=\"ui_arrow arrow-" + o.arrow + "-in\" style=\"z-index:2;\"></span><i class=\"ui_tips_close\">x</i>";
            $contentType = o.content.substring(0, o.content.indexOf(":"));
            //$content = o.type == "tips" ? "<div class='ui_tips_content'><i class=\"ui_tips_content_ico\"></i>"+o.content.substring(o.content.indexOf(":")+1,o.content.length)+"</div>" + tipsDom: o.content.substring(o.content.indexOf(":")+1,o.content.length);			
            switch (o.type) {
                case "dialog":
                    var conObj = o.content.substring(o.content.indexOf(":") + 1, o.content.length);//取内容对像的DIV
                    $content = conObj.substring(0, 1) == "#" ? $(conObj).html() : o.content.substring(o.content.indexOf(":") + 1, o.content.length);
                    break;

                case "tips":
                    var conObj = o.content.substring(o.content.indexOf(":") + 1, o.content.length);//取内容对像的DIV
                    var popHtml = conObj.substring(0, 1) == "#" ? $(conObj).html() : o.content.substring(o.content.indexOf(":") + 1, o.content.length);
                    $content = "<div class='ui_tips_content'>" + popHtml + "</div>" + tipsDom;
                    break;
                    /*case "overried":
                         var conObj=o.content.substring(o.content.indexOf(":")+1,o.content.length);//取内容对像的DIV
                         $content=conObj.substring(0,1)=="#"?$(conObj).html():o.content.substring(o.content.indexOf(":")+1,o.content.length);
                         break;*/
            }
            $.ajaxSetup({ global: false });
            var _width = o.width != "" ? o.width : "auto", _height = o.height != "" ? o.height : "auto";
            $contentID.css({
                width: _width,
                height: _height
            });

            var drag = function (dragBox) {
                winarr.push([o.boxID, WinDialog.getID(o.boxID).style.zIndex, $contentID.width(), $contentID.height()]);
                if (!dragBox) return;
                var safe = WinDialog.safeRange(o.boxID);
                var tempBox = safe.width > 400 || safe.height > 300 ? ".ui_move_temp" : "";
                WinDialog.loadJS("windrag.js", function () {
                    Windrag({
                        obj: o.boxID,
                        handle: ".ui_title_text",
                        lock: o.lock,
                        fixed: o.fixed,
                        temp: tempBox
                    });
                });
            };
            switch ($contentType) {
                case "prompt":
                    //var $content='[{"style":"1","msg":"显示正常"}]';
                    var json = $.parseJSON($content);
                    var style = "1";//默认图标
                    var msg = "信息提示信息";
                    if (WinDialog.type(json) === "object") {
                        style = json.style;
                        msg = json.msg;
                    }
                    var html = "<div class=\"ui_ico_s" + style + "\"><em></em><span>" + msg + "<span></div>";
                    $contentID.html(html);
                    WinDialog.setPosition(o);
                    drag(o.drag);
                    if (o.openCallback != "" && $.isFunction(o.openCallback)) o.openCallback(this);
                    break;
                case "text":
                    $contentID.html($content);
                    WinDialog.setPosition(o);
                    drag(o.drag);
                    if (o.openCallback != "" && $.isFunction(o.openCallback)) o.openCallback(this);
                    break;
                case "url":
                      var contentDate = $content.split("?");
                    $.ajax({
                        dataType: "html",
                        beforeSend: function () {
                            $contentID.html("<img src='' class='ui_box_loading' alt='加载中...' />");
                            WinDialog.setPosition(o);
                        },
                        type: contentDate[0],
                        url: contentDate[1],
                        data: contentDate[2],
                        error: function () {
                            $contentID.html("<p class='ui_box_error'><span class='ui_box_callback_error'></span>加载数据出错！</p>");
                            WinDialog.setPosition(o);
                        },
                        success: function (html) {
                            $contentID.html(html);
                            WinDialog.setPosition(o);
                            drag(o.drag);
                            if (o.openCallback != "" && $.isFunction(o.openCallback)) o.openCallback(this);
                        }
                    });
                    break;
                case "iframe":
                    $.ajax({
                        dataType: "html",
                        beforeSend: function () {
                            //$contentID.html("<img src='" + Util.config.loadingICO + "' class='ui_box_loading' alt='加载中...' />")
                            $contentID.html("<img src='' class='ui_box_loading' alt='加载中...' />")
                            WinDialog.setPosition(o);
                        },
                        error: function () {
                            $contentID.html("<p class='ui_box_error'><span class='ui_box_callback_error'></span>加载数据出错！</p>");
                            WinDialog.setPosition(o);
                        },
                        success: function (html) {
                            _this.find(".ui_button_wrap").hide();
                            $contentID.html("<iframe src=\"" + $content + "\" name=\"" + o.boxID + "frame\" id=\"" + o.boxID + "frame\" style=\"width:100%;height:100%\" scrolling=\"auto\" frameborder=\"0\"></iframe>");
                            $("#" + o.boxID + "frame").bind("load", function () {
                                var frame = document.getElementById(o.boxID + "frame");
                                var obj = WinDialog.iframeSize(frame);
                                //求宽
                                if (o.width != "") {
                                    _this.find(".ui_content").css({ width: obj.Width + "px" });//如果没有设宽，则取iframe自适应宽
                                } else {
                                    _this.find(".ui_content").css({ width: _width + "px" });
                                }
                                //求高
                                if (o.height != "") {
                                    _this.find(".ui_content").css({ height: obj.Height + "px" });//如果没有设高，则取iframe自适应高

                                }
                                else {
                                    _this.find(".ui_content").css({ height: _height + "px" });
                                }
                                if (o.openCallback != "" && $.isFunction(o.openCallback)) o.openCallback(this);
                            });
                        }
                    });
                    break;
                case "login":
                    $(".ui_table_wrap", _this).remove();
                    $.ajax({
                        dataType: "html",
                        beforeSend: function () {
                            _this.html("<img src='' class='ui_box_loading' alt='加载中...' />")
                            WinDialog.setPosition(o);
                        },
                        error: function () {
                            _this.html("<p class='ui_box_error'><span class='ui_box_callback_error'></span>加载数据出错！</p>");
                            WinDialog.setPosition(o);
                        },
                        success: function (html) {
                            _this.html("<iframe scrolling=\"no\" frameborder=\"no\" allowtransparency=\"true\" src=\"" + $content + "\" name=\"" + o.boxID + "frame\" id=\"" + o.boxID + "frame\" style=\"width:100%;height:100%\"></iframe>");
                            $("#" + o.boxID + "frame").bind("load", function () {
                                var frame = document.getElementById(o.boxID + "frame");
                                var obj = WinDialog.iframeSize(frame);
                                //求宽
                                if (o.width == "") {
                                    _this.css({ width: obj.Width + "px" });//如果没有设宽，则取iframe自适应宽
                                } else {
                                    _this.css({ width: _width + "px" });
                                }
                                //求高
                                if (o.height == "") {
                                    _this.css({ height: obj.Height + "px" });//如果没有设高，则取iframe自适应高
                                }
                                else {
                                    _this.css({ height: _height + "px" });
                                }
                                WinDialog.setPosition(o);
                                drag(o.drag);
                                if (o.openCallback != "" && $.isFunction(o.openCallback)) o.openCallback(this);
                            });
                        }
                    });
            };
        },
        iframeSize: function (frame) {
            var obj = {};
            var errorIframe = frame;
            try {
                var frame = frame.contentWindow.document;
                obj.Width = Math.max(frame.body.scrollWidth, frame.documentElement.scrollWidth);
                obj.Height = Math.max(frame.body.scrollHeight, frame.documentElement.scrollHeight); //计算宽度和高度
            } catch (e) {
                obj.Height = errorIframe.offsetHeight;
                obj.Width = errorIframe.offsetWidth;
            }
            return obj;
        },

        setPosition: function (o) {
            WinDialog.setXY(o.boxID, o.position, o.referID, o.fixed);
            var safe = WinDialog.safeRange(o.boxID);
            $(".ui_iframe", _this).css({
                width: safe.width + "px",
                height: safe.height + "px"
            });
            if (o.type == "tips") {
                var t = o.tips, mode = o.arrow == "left" || o.arrow == "right" ? "top" : "left";
                var val = t.val || "10";
                var style = t.style || "default";
                var radius = t.radius || "0";
                var auto = t.auto && true;
                _this.find(".ui_button_wrap").hide().end()
                .find(".ui_dialog_main").css({ border: "none", background: "none" })
                .find(".ui_content").addClass("ui_tips_style_" + style).css({ borderRadius: radius + "px", textAlign: "left" })
                .find(".ui_arrow").css(mode, val + "px").end()
                .find(".ui_tips_close").click(function () {
                    WinDialog.webclose(o.boxID, o.closeCallback, o.closestyle);
                });
                var ob = WinDialog.getPosition(o.boxID), rp = WinDialog.getPosition(o.referID), s = WinDialog.safeRange(o.referID), st = document.body.scrollTop || document.documentElement.scrollTop;
                switch (o.arrow) {
                    case "left":
                        _this.css({
                            left: ob.x + 8 + "px",
                            top: ob.y + "px"
                        });
                        if (auto == true && p.clientWidth - ob.x < _this.outerWidth()) {
                            _this.css({
                                left: rp.x - _this.outerWidth() - 8
                            }).find(".ui_arrow").removeClass("ui_arrow_mode_left").addClass("ui_arrow_mode_right");
                        };
                        break;
                    case "right":
                        _this.css({
                            left: ob.x - 10 + "px",
                            top: ob.y + "px"
                        });
                        if (auto == true && ob.x < 0) {
                            _this.css({
                                left: rp.x + s.width + 8
                            }).find(".ui_arrow").removeClass("ui_arrow_mode_right").addClass("ui_arrow_mode_left");
                        };
                        break;
                    case "bottom":
                        _this.css({
                            left: ob.x + "px",
                            top: ob.y - 8 + "px"
                        });
                        if (auto == true && ob.y < 0) {
                            _this.css({
                                top: rp.y + s.height + 8
                            }).find(".ui_arrow").removeClass("ui_arrow_mode_bottom").addClass("ui_arrow_mode_top");
                        };
                        break;
                    case "top":
                        _this.css({
                            left: ob.x + "px",
                            top: ob.y + 8 + "px"
                        });
                        if (auto == true && p.clientHeight - ob.y + st < _this.outerHeight()) {
                            _this.css({
                                top: rp.y - _this.outerHeight() - 8
                            }).find(".ui_arrow").removeClass("ui_arrow_mode_top").addClass("ui_arrow_mode_bottom");
                        };
                        break;
                };
            };
        },
        yesBtn: function (o) {
            var fn = o.yesBtn[1] || function () { },
            text = o.yesBtn[0] || "\u786E\u5B9A";
            var yesBtnDom = "<button class=\"ui_box_btn ui_box_btn_yes\">" + text + "</button>";
            _this.find(".ui_button_wrap").append(yesBtnDom);
            if (fn != "" && $.isFunction(fn)) {
                _this.find(".ui_box_btn_yes").click(function () {
                    var f = fn();
                    if (f != false) WinDialog.webclose(o.boxID, o.closeCallback, o.closestyle);// 如果回调函数返回false则不关闭对话框
                });
            };
        },
        noBtn: function (o) {
            var fn = o.noBtn[1] || function () { },
            text = o.noBtn[0] || "\u53D6\u6D88";
            var noBtnDom = "<button class=\"ui_box_btn ui_box_btn_no\">" + text + "</button>";
            _this.find(".ui_button_wrap").append(noBtnDom);
            if (fn != "" && $.isFunction(fn)) {
                _this.find(".ui_box_btn_no").click(function () {
                    var f = fn();
                    if (f != false) WinDialog.webclose(o.boxID, o.closeCallback, o.closestyle);// 如果回调函数返回false则不关闭对话框
                });
            };
        },
        valmin: function (o) {
            var _this = $("#" + o.boxID);
            $(".ui_btn_min", _this).on("click", function () {
                _this.find(".ui_content").css({
                    width: "0",
                    height: "0",
                    display: "none",
                    visibility: "hidden"
                }).end().find(".ui_button_wrap").hide();
                var safe = WinDialog.safeRange(o.boxID);
                $(".ui_iframe", _this).css({
                    width: safe.width + "px",
                    height: safe.height + "px"
                });
                _this.addClass("ui_dialog_min").removeClass("ui_dialog_restore ui_dialog_max");
                return false;
            });
        },
        valmax: function (o) {
            var _this = $("#" + o.boxID);
            $(".ui_btn_max", _this).on("click", function () {
                var p = WinDialog.pageSizeGet();
                w = p.clientWidth - (o.showborder ? 10 : 2);
                h = p.clientHeight - (o.showtitle ? 34 : 2) - (o.button ? 36 : 0);
                _this.find(".ui_content").css({
                    width: w + "px",
                    height: h + "px"
                });
                WinDialog.setPosition(o);
                _this.addClass("ui_dialog_max").removeClass("ui_dialog_restore ui_dialog_min");
                if (o.drag) {
                    _this.find(".ui_title_text").css("cursor", "default");
                }
                return false;
            });
        },
        restore: function (o) {
            var _this = $("#" + o.boxID);
            var winarr = WinDialog.data.winarr;
            $(".ui_btn_restore", _this).on("click", function (){
               /* for (var i = 0; i < winarr.length; i++) {
                    if (o.boxID == winarr[i][0]) {
                        _this.find(".ui_content").css({
                            width: winarr[i][1] + "px",
                            height: winarr[i][2] + "px",
                            display: "block",
                            visibility: "visible"
                        }).end().find(".ui_button_wrap").show();
                        WinDialog.setPosition(o);
                        _this.addClass("ui_dialog_restore").removeClass("ui_dialog_min ui_dialog_max");
                    };
                };*/
				 _this.find(".ui_content").css({
                            width:o.width+ "px",
                            height:o.height+ "px",
                            display: "block",
                            visibility: "visible"
                        }).end().find(".ui_button_wrap").show();
                 WinDialog.setPosition(o);
                 _this.addClass("ui_dialog_restore").removeClass("ui_dialog_min ui_dialog_max");						
                if (o.drag) {
                    _this.find(".ui_title_text").css("cursor", "move");
                };
                return false;
            });
        },
        //关闭弹窗
        webclose: function (obj, closeCallback, closestyle) {
            if (typeof obj === "string") {
                box = $("#" + obj);
            } else {
                alert("请指定弹出窗口的ID！");
                return;
            };
            if (box.length != 0) {
                //指定关闭窗口特效
                if (closestyle == "1") {
                    box.parent().remove();
                    $("#PopWindowBg").remove();

                }else{ box.parent().remove(); }
                for (var i = 0; i < WinDialog.data.winarr.length; i++) {
                    if (obj == WinDialog.data.winarr[i][0]) WinDialog.data.winarr.remove(WinDialog.data.winarr[i]);
                };
                if (closeCallback != "" && $.isFunction(closeCallback)) {
                    closeCallback(this);
                };
            };
        }
    });
})(jQuery)