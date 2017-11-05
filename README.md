1. install python3.6
```bash
apt install -y software-properties-common
add-apt-repository ppa:jonathonf/python-3.6  # Press [ENTER] to continue
apt update
apt install -y python3.6 python3.6-dev python3.6-venv
```


2. install python3.6-setuptools
```bash
apt install -y unzip
wget https://pypi.python.org/packages/45/29/8814bf414e7cd1031e1a3c8a4169218376e284ea2553cc0822a6ea1c2d78/setuptools-36.6.0.zip#md5=74663b15117d9a2cc5295d76011e6fd1
unzip setuptools-36.6.0.zip
cd setuptools-36.6.0/
python3.6 setup.py install
```


3. install python3.6-pip
```bash
wget https://pypi.python.org/packages/11/b6/abcb525026a4be042b486df43905d6893fb04f05aac21c32c638e939e447/pip-9.0.1.tar.gz#md5=35f01da33009719497f01a4ba69d63c9
tar zxvf pip-9.0.1.tar.gz
cd pip-9.0.1/
python3.6 setup.py install
```


4. mkdir directories
```bash
cd ~
mkdir -p ~/data/logs/proxy
mkdir -p ~/data/logs/supervisor
mkdir -p ~/data/logs/taobao/cron_tasks
```


5. clone source
```bash
apt install -y git
cd ~/data/
git clone https://github.com/capric8416/taobao
git clone https://github.com/capric8416/proxy_swift
git clone https://github.com/capric8416/ProxySwiftMaster
```


6. install requirements
```bash
cd ~/data/taobao
python3.6 -m venv env1
env1/bin/pip install -r requirements.txt
python3.6 -m venv env2
env2/bin/pip install -r requirements.txt
```


7. install supervisor
```bash
apt install -y supervisor
cd /etc/
rm -rf supervisor/
ln -s ~/data/taobao/system/etc/supervisor .
supervisord -c /etc/supervisor/supervisord.conf
```


8. update environment
```bash
append ~/data/taobao/system/etc/profile content to /etc/profile
source /etc/profile
```


9. update cron
```bash
crontab -e
append ~/data/taobao/system/cron content to it  # make sure a new line at the end
save & exit
```


10. view status
```bash
supervisorctl status all
```


11. start/stop/restart/status service
```bash
supervisorctl start/stop/restart/status service_name  # all services name will shown when you type supervisorctl status all
```


12. view logs
```bash
all logs file locate in ~/data/logs
tail -f log_file_path will dynamic show latest logs
```



