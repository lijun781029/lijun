from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.spinner import Spinner
from kivy.uix.scrollview import ScrollView
from kivy.uix.popup import Popup
from kivy.uix.textinput import TextInput
from kivy.uix.gridlayout import GridLayout
from kivy.core.window import Window
from kivy.utils import platform
from kivy.clock import Clock
from kivy.properties import StringProperty, ListProperty, BooleanProperty
from kivy.metrics import dp
from kivy.graphics import Color, Rectangle

import requests
import json
from datetime import datetime, date
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import os
import re
import threading
import time

# 设置移动端适配
if platform == 'android':
    from android.permissions import request_permissions, Permission
    request_permissions([Permission.INTERNET, Permission.WRITE_EXTERNAL_STORAGE])

class OilPriceApp(App):
    api_sources = ListProperty([
        {"name": "聚合数据", "id": "juhe", "needs_key": True},
        {"name": "10260油价网", "id": "10260", "needs_key": False}
    ])
    provinces_data = ListProperty([])
    cities_data = ListProperty([])
    status_text = StringProperty("准备就绪 | 请选择数据源和地区")
    result_text = StringProperty("")
    calendar_dates = ListProperty([])
    
    def build(self):
        # 设置窗口背景色
        Window.clearcolor = (0.95, 0.95, 0.95, 1)
        
        # 主布局
        main_layout = BoxLayout(orientation='vertical', spacing=dp(10), padding=dp(10))
        
        # 顶部控制面板
        control_layout = GridLayout(cols=1, spacing=dp(10), size_hint=(1, None), height=dp(200))
        
        # API选择
        self.api_spinner = Spinner(
            text='聚合数据',
            values=[source['name'] for source in self.api_sources],
            size_hint=(1, None),
            height=dp(50)
        )
        
        # 省份选择
        self.province_spinner = Spinner(
            text='四川省',
            values=[],
            size_hint=(1, None),
            height=dp(50)
        )
        self.province_spinner.bind(text=self.on_province_select)
        
        # 城市选择
        self.city_spinner = Spinner(
            text='广元市',
            values=[],
            size_hint=(1, None),
            height=dp(50)
        )
        
        # 查询按钮
        query_btn = Button(
            text='查询油价',
            size_hint=(1, None),
            height=dp(50),
            background_color=(0.12, 0.56, 1, 1),
            color=(1, 1, 1, 1)
        )
        query_btn.bind(on_press=self.query_price)
        
        # 添加到控制面板
        control_layout.add_widget(self.api_spinner)
        control_layout.add_widget(self.province_spinner)
        control_layout.add_widget(self.city_spinner)
        control_layout.add_widget(query_btn)
        
        # 状态标签
        status_label = Label(
            text=self.status_text,
            size_hint=(1, None),
            height=dp(30),
            color=(0.4, 0.4, 0.4, 1),
            font_size=dp(14)
        )
        self.bind(status_text=status_label.setter('text'))
        
        # 结果显示区域
        result_scroll = ScrollView(size_hint=(1, 1))
        self.result_label = Label(
            text=self.result_text,
            size_hint_y=None,
            valign='top',
            halign='left',
            markup=True,
            padding=(dp(10), dp(10)),
            text_size=(Window.width - dp(20), None)
        )
        self.result_label.bind(texture_size=self.result_label.setter('size'))
        self.bind(result_text=self.result_label.setter('text'))
        result_scroll.add_widget(self.result_label)
        
        # 底部按钮栏
        button_layout = BoxLayout(size_hint=(1, None), height=dp(50), spacing=dp(10))
        history_btn = Button(text='历史记录', size_hint=(0.5, 1))
        history_btn.bind(on_press=self.show_history)
        scfgw_btn = Button(text='四川发改委', size_hint=(0.5, 1))
        scfgw_btn.bind(on_press=self.download_scfgw_file)
        button_layout.add_widget(history_btn)
        button_layout.add_widget(scfgw_btn)
        
        # 添加到主布局
        main_layout.add_widget(control_layout)
        main_layout.add_widget(status_label)
        main_layout.add_widget(result_scroll)
        main_layout.add_widget(button_layout)
        
        # 初始化数据
        self.load_provinces()
        self.load_calendar_dates()
        self.display_calendar()
        
        return main_layout
    
    def load_provinces(self):
        """加载省份数据"""
        self.provinces_data = sorted(self.load_full_china_cities().keys())
        self.province_spinner.values = self.provinces_data
    
    def load_full_china_cities(self):
        """加载完整的中国省市数据"""
        return {
            "北京市": ["东城区", "西城区", "朝阳区", "丰台区", "石景山区", "海淀区", "顺义区", "通州区", "大兴区",
                     "房山区", "门头沟区", "昌平区", "平谷区", "密云区", "延庆区"],
            # ... 其他省份数据与原始代码相同 ...
            "四川省": ["成都市", "自贡市", "攀枝花市", "泸州市", "德阳市", "绵阳市", "广元市", "遂宁市", "内江市",
                     "乐山市", "南充市", "眉山市", "宜宾市", "广安市", "达州市", "雅安市", "巴中市", "资阳市",
                     "阿坝藏族羌族自治州", "甘孜藏族自治州", "凉山彝族自治州"],
            # ... 其他省份数据 ...
        }
    
    def on_province_select(self, instance, value):
        """省份选择事件"""
        cities = self.load_full_china_cities().get(value, [])
        self.cities_data = sorted(cities)
        self.city_spinner.values = self.cities_data
        if cities:
            self.city_spinner.text = cities[0]
    
    def load_calendar_dates(self):
        """加载油价调整日历数据"""
        try:
            if os.path.exists('oil_calendar.json'):
                with open('oil_calendar.json', 'r') as f:
                    dates = json.load(f)
                    # 过滤掉已过期的日期
                    today = date.today().isoformat()
                    self.calendar_dates = [d for d in dates if d >= today]
            else:
                self.calendar_dates = [
                    "2025-01-02", "2025-01-16",
                    "2025-02-06", "2025-02-19",
                    # ... 其他日期 ...
                ]
        except:
            self.calendar_dates = []
    
    def save_calendar_dates(self):
        """保存油价调整日历数据"""
        with open('oil_calendar.json', 'w') as f:
            json.dump(self.calendar_dates, f)
    
    def display_calendar(self):
        """显示油价调整日历"""
        today = date.today().isoformat()
        future_dates = [d for d in sorted(self.calendar_dates) if d >= today]
        
        calendar_text = "[b]油价调整日历[/b]\n\n"
        if future_dates:
            calendar_text += "\n".join(future_dates) + "\n"
        else:
            calendar_text += "暂无未来油价调整计划\n"
        
        calendar_text += "\n" + "=" * 30 + "\n"
        self.result_text = calendar_text
    
    def query_price(self, instance):
        """查询油价"""
        api_name = self.api_spinner.text
        province = self.province_spinner.text
        city = self.city_spinner.text
        
        self.status_text = f"正在查询 {province}{city} 油价..."
        
        # 在后台线程中执行查询
        threading.Thread(
            target=self._query_price_background,
            args=(api_name, province, city),
            daemon=True
        ).start()
    
    def _query_price_background(self, api_name, province, city):
        """后台查询油价"""
        try:
            data = None
            if api_name == "聚合数据":
                data = self.query_juhe_api(province, city)
            elif api_name == "10260油价网":
                data = self.query_10260_price(province, city)
            
            if data:
                self.display_result(province, city, data, api_name)
                self.save_to_history(province, city, data, api_name)
                self.status_text = f"查询成功 | {datetime.now().strftime('%H:%M:%S')}"
            else:
                self.status_text = "查询完成但未获取到数据"
        except Exception as e:
            self.status_text = f"查询失败: {str(e)}"
    
    def query_juhe_api(self, province, city):
        """查询聚合数据API"""
        # 这里需要配置你的聚合数据API密钥
        api_key = ""  # 请在此处填写你的聚合数据API密钥
        
        if not api_key:
            raise ValueError("请先配置聚合数据API密钥")
        
        params = {
            'key': api_key,
            'province': province.replace("省", "").replace("市", "")
        }
        if city:
            params['city'] = city.replace("市", "").replace("区", "").replace("县", "")
        
        response = requests.get('http://apis.juhe.cn/gnyj/query', params=params, timeout=10)
        response.raise_for_status()
        result = response.json()
        
        if result.get('error_code') != 0:
            raise ValueError(f"API错误: {result.get('reason', '未知错误')}")
        
        search_name = city if city else province
        clean_search_name = search_name.replace("省", "").replace("市", "").replace("区", "").replace("县", "")
        
        matched_data = None
        for item in result['result']:
            if isinstance(item, dict) and item.get('city') == clean_search_name:
                matched_data = item
                break
        
        if not matched_data:
            raise ValueError(f"未找到{search_name}的油价数据")
        
        return {
            'source': "聚合数据",
            'update_time': datetime.now().strftime("%Y-%m-%d %H:%M"),
            'prices': [
                ("92号汽油", matched_data.get('92h', '--')),
                ("95号汽油", matched_data.get('95h', '--')),
                ("98号汽油", matched_data.get('98h', '--')),
                ("0号柴油", matched_data.get('0h', '--'))
            ],
            'note': "数据来自聚合数据API，实际价格可能有波动"
        }
    
    def query_10260_price(self, province, city):
        """查询10260油价网数据"""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get('http://youjia.10260.com/', headers=headers, timeout=10)
        response.encoding = 'gbk'
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        price_table = soup.find('table', {'bgcolor': '#B6CCE4'})
        
        if not price_table:
            raise ValueError("未找到油价数据表格")
        
        prices = {}
        for row in price_table.find_all('tr')[1:]:
            cols = row.find_all('td')
            if len(cols) >= 5:
                region = cols[0].get_text(strip=True)
                price_92 = cols[1].get_text(strip=True)
                price_95 = cols[2].get_text(strip=True)
                price_98 = cols[3].get_text(strip=True)
                price_0 = cols[4].get_text(strip=True)
                update_time = cols[5].get_text(strip=True) if len(cols) > 5 else "未知"
                
                prices[region] = {
                    '92号汽油': price_92,
                    '95号汽油': price_95,
                    '98号汽油': price_98,
                    '0号柴油': price_0,
                    '更新时间': update_time
                }
        
        province_clean = province.replace("省", "").replace("市", "").replace("自治区", "").replace("特别行政区", "")
        city_clean = city.replace("市", "").replace("区", "").replace("县", "")
        
        matched_data = None
        for region in prices:
            if province_clean in region or (city_clean and city_clean in region):
                matched_data = prices[region]
                break
        
        if not matched_data:
            for region in prices:
                if province_clean in region:
                    matched_data = prices[region]
                    break
        
        if not matched_data:
            raise ValueError(f"未找到{province}{city if city else ''}的油价数据")
        
        return {
            'source': "10260油价网",
            'update_time': matched_data.get('更新时间', datetime.now().strftime("%Y-%m-%d %H:%M")),
            'prices': [
                ("92号汽油", matched_data.get('92号汽油', '--')),
                ("95号汽油", matched_data.get('95号汽油', '--')),
                ("98号汽油", matched_data.get('98号汽油', '--')),
                ("0号柴油", matched_data.get('0号柴油', '--'))
            ],
            'note': "数据来自10260油价网，仅供参考"
        }
    
    def display_result(self, province, city, data, api_source):
        """显示查询结果"""
        location = f"{province}{' ' + city if city else ''}"
        result_text = f"[b][color=#1E90FF]{location} 最新油价 ({data['source']})[/color][/b]\n\n"
        result_text += f"[color=#666666]更新时间: {data['update_time']}[/color]\n\n"
        
        max_name_length = max(len(name) for name, _ in data['prices'])
        for name, price in data['prices']:
            result_text += f"[b]{name:>{max_name_length + 2}}: [/b][color=#FF4500]{price:>6} 元/升[/color]\n"
        
        if data.get('note'):
            result_text += f"\n[color=#666666][size=12]{data['note']}[/size][/color]"
        
        result_text += "\n\n" + "=" * 30 + "\n"
        result_text += "[color=#666666][size=12]数据仅供参考，实际价格以当地加油站为准[/size][/color]"
        
        # 保留日历内容
        self.result_text = self.result_text.split("=")[0] + result_text
    
    def save_to_history(self, province, city, data, api_source):
        """保存查询历史"""
        history = []
        history_file = 'oil_history.json'
        
        if os.path.exists(history_file):
            try:
                with open(history_file, 'r', encoding='utf-8') as f:
                    history = json.load(f)
            except:
                history = []
        
        record = {
            'province': province,
            'city': city,
            'data': data,
            'api_source': api_source,
            'query_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        history.insert(0, record)
        if len(history) > 100:
            history = history[:100]
        
        with open(history_file, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    
    def show_history(self, instance):
        """显示查询历史"""
        history = []
        history_file = 'oil_history.json'
        
        if os.path.exists(history_file):
            try:
                with open(history_file, 'r', encoding='utf-8') as f:
                    history = json.load(f)
            except:
                history = []
        
        content = BoxLayout(orientation='vertical', spacing=dp(10), padding=dp(10))
        scroll = ScrollView(size_hint=(1, 1))
        history_layout = GridLayout(cols=1, spacing=dp(5), size_hint_y=None)
        history_layout.bind(minimum_height=history_layout.setter('height'))
        
        if not history:
            history_layout.add_widget(Label(text="暂无查询历史", size_hint_y=None, height=dp(50)))
        else:
            for record in history[:20]:  # 只显示最近的20条记录
                time_str = record['query_time']
                location = f"{record['province']}{' ' + record['city'] if record['city'] else ''}"
                btn = Button(
                    text=f"{time_str} - {location}",
                    size_hint_y=None,
                    height=dp(50)),
                background_color=(0.9, 0.9, 0.9, 1)
                
                btn.bind(on_press=lambda b, r=record: self.show_history_detail(r))
                history_layout.add_widget(btn)
        
        scroll.add_widget(history_layout)
        content.add_widget(scroll)
        
        close_btn = Button(text='关闭', size_hint=(1, None), height=dp(50))
    
        content.add_widget(close_btn)
        
        popup = Popup(
            title='查询历史记录',
            content=content,
            size_hint=(0.9, 0.8)
        )
        close_btn.bind(on_press=popup.dismiss)
        popup.open()
    
    def show_history_detail(self, record):
        """显示历史记录详情"""
        self.display_result(
            record['province'],
            record['city'],
            record['data'],
            record['api_source']
        )
    
    def download_scfgw_file(self, instance):
        """下载四川发改委文件"""
        self.status_text = "正在获取四川发改委成品油价格通知..."
        
        threading.Thread(
            target=self._download_scfgw_background,
            daemon=True
        ).start()
    
    def _download_scfgw_background(self):
        """后台下载四川发改委文件"""
        try:
            notices = self.get_oil_price_notices()
            
            if not notices:
                self.status_text = "未找到四川发改委成品油价格通知"
                return
            
            latest_notice = notices[0]  # 最新的通知
            
            self.status_text = f"正在下载: {latest_notice[1]}..."
            
            # 这里简化处理，实际应用中应该实现文件下载
            self.status_text = f"已获取通知: {latest_notice[1]}"
            
            # 显示通知内容
            self.result_text += f"\n\n[b]四川发改委通知[/b]\n{latest_notice[1]}\n{latest_notice[2]}"
        except Exception as e:
            self.status_text = f"获取四川发改委文件失败: {str(e)}"
    
    def get_oil_price_notices(self):
        """获取成品油价格通知列表"""
        base_url = "https://fgw.sc.gov.cn/"
        shehui_url = urljoin(base_url, "sfgw/c106084/common_list.shtml")
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(shehui_url, headers=headers, timeout=15)
        response.encoding = 'utf-8'
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        notices = []
        
        list_wrap = soup.find('ul', class_='list')
        if list_wrap:
            for item in list_wrap.find_all('li'):
                date_span = item.find('span')
                link = item.find('a')
                
                if date_span and link:
                    date_text = date_span.get_text().strip()
                    title = link.get_text().strip()
                    href = link.get('href')
                    
                    keywords = ['成品油', '油价', '川发改价格']
                    if any(keyword in title for keyword in keywords) and href:
                        date_match = re.search(r'(\d{4}-\d{2}-\d{2})', date_text)
                        if date_match:
                            notice_date = datetime.strptime(date_match.group(1), '%Y-%m-%d')
                            notice_url = urljoin(shehui_url, href)
                            notices.append((notice_date, title, notice_url))
        
        if not notices:
            raise Exception("未找到符合条件的通知")
            
        return sorted(notices, key=lambda x: x[0], reverse=True)[:5]

if __name__ == '__main__':
    OilPriceApp().run()