# Virtual Patient Integration Server

This project implements a simple web service that integrates machine learning-based
dialog responses from [a text CNN](https://github.com/OSU-slatelab/vp-cnn) and rule-
based responses from [a ChatScript](https://github.com/OSU-slatelab/vp-chatscript)
instance.

## Dependencies

* Flask
* Flask-CORS
* Flask-MySQLDB
* gevent
* pytorch v0.12
* scipy
* a separate MySQL (MariaDB) instance

## Funding notice and disclaimer

This material is partially based upon work supported by the National Science
Foundation under Grant Number 1618336. Any opinions, findings, and conclusions or
recommendations expressed in this material are those of the author(s) and do not
necessarily reflect the views of the National Science Foundation.