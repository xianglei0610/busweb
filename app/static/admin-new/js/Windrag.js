/*
	拖拽
	Date：2013-11-06
	Author：Kalven
	CopyRight:www.12308.com
*/
;(function($){
Windrag = function (o) {
	var defaults = {
		obj: "", 
		handle: "", 
		lock: true, 
		lockX: false, 
		lockY: false,
		fixed: false,
		drag:true,
		parent: "",
		temp:"",
		dstar: function () {},
		dmove: function () {},
		dstop: function () {}
	};
	Windrag.browser=function (){
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
         }();
	Windrag.pageSizeGet=function () {
				var a = WinDialog.browser.isStrict ? document.documentElement : document.body;
				var b = ["clientWidth", "clientHeight", "scrollWidth", "scrollHeight"];
				var c = {};
				for (var d in b) c[b[d]] = a[b[d]];
				c.scrollLeft = document.body.scrollLeft || document.documentElement.scrollLeft;
				c.scrollTop = document.body.scrollTop || document.documentElement.scrollTop;
				return c
		};
	Windrag.getPosition=function (obj) {
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
		};
	Windrag.safeRange=function (obj) {
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
			//alert(g+"|"+h)
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
		};
	Windrag.getID=function (id){return document.getElementById(id);};
		
	var o = $.extend(defaults, o);
	var _x, _y, _d, otemp,
	mx = my = 0,
	_this = $("#" + o.obj);
	_d = o.handle != "" ? $(o.handle, _this) : _this;
	_d.css("cursor", "move");
	_d.mousedown(function (ev) {
		if (!o.drag) return;
		safe = Windrag.safeRange(o.obj);
		tempBox = _this.parent().find(o.temp);
		s = Windrag.pageSizeGet();
		otemp = o.temp!="" ? tempBox : _this;
		star(ev);
		if(o.obj.setCapture){
			o.obj.setCapture();
		}else if(window.captureEvents){
			window.captureEvents(Event.MOUSEMOVE|Event.MOUSEUP);
		};
		$(document).bind("mousemove", function(ev){move(ev);});
		$(document).bind("mouseup", function(ev){stop(ev);});
	});
	if (o.fixed) o.parent = "";
	if (o.parent != "")$("#" + o.parent).css("position", "relative");
	var	star = function (ev) {
		ev = ev || window.event;
		ev.preventDefault();
		p = Windrag.getPosition(o.obj);
		ny = o.fixed ? Windrag.browser.isIE6 ? s.scrollTop : 0 : 0;
		mx = ev.clientX - p.x;
		my = ev.clientY - p.y + ny;
		if (o.temp!=""){
			otemp.css({
				left : p.x + "px",
				top: p.y + ny + "px",
				width: safe.width + "px",
				height: safe.height + "px",
				display: "block"
			});
		};
		if (o.dstar != "" && $.isFunction(o.dstar)) o.dstar(this);
		_this.addClass("ui_drag_start").removeClass("ui_drag_move ui_drag_stop");
	},
	move = function(ev){
		var parent;
		ev = ev || window.event;
		window.getSelection ? window.getSelection().removeAllRanges() : document.selection.empty();
		_x = ev.clientX - mx;
		_y = ev.clientY - my;
		if (o.parent != "") {
			parent = Windrag.getPosition(o.parent);
			op = Windrag.getPosition(o.obj);
			_x = ev.clientX - mx - parent.x ;
			_y = ev.clientY - my - parent.y ;
		};
		maxX = o.parent != "" ? parent.width - op.width : safe.maxX;
		maxY = o.parent != "" ? parent.height - op.height : safe.maxY;
		if (o.lockX) _y = p.y;
		if (o.lockY) _x = p.x;
		if (o.lock) {
			if (_x <= 0) _x = safe.minX;
			if (_x >= maxX) _x = maxX;
			if (o.fixed){
				if (_y <= 0) _y = safe.minY;
				if (_y >= maxY)_y = maxY;
			}else{
				if ( _y > maxY+s.scrollTop) _y = maxY+s.scrollTop;
				if ( _y < s.scrollTop)_y = s.scrollTop; 
			};
		};
		otemp.css({
			left: _x  + "px",
			top: _y  + "px"
		});
		_this.addClass("ui_drag_move").removeClass("ui_drag_start ui_drag_stop");
		if (o.dmove != "" && $.isFunction(o.dmove)) o.dmove(this);
	},
	stop = function(ev){
		if (o.temp !="" && o.drag){
			otemp.css("display","none");
			_this.css({
				left: _x + "px",
				top: _y + "px"
			});
		};
		_this.addClass("ui_drag_stop").removeClass("ui_drag_start ui_drag_move");
		$(document).unbind("mousemove");
		if(o.obj.releaseCapture) {
			o.obj.releaseCapture();
        } else if(window.captureEvents) {
			window.captureEvents(Event.MOUSEMOVE|Event.MOUSEUP);
        }
		if (o.dstop != "" && $.isFunction(o.dstop)) o.dstop(this);
	};
};
})(jQuery)