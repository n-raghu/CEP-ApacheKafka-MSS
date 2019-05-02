from msgpack import packb
from random import randint
from flask import jsonify, abort, request, make_response, Flask
from flask_restful import Api,Resource
from flask_jwt_extended import (JWTManager, jwt_required, create_access_token,get_jwt_identity)
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine as dbeng,text as alchemyText
from datetime import datetime as dtm,timedelta as tdt
from confluent_kafka import Producer,Consumer,KafkaError
from model import Account as A
from yaml import safe_load

with open('app.yml') as ymlFile:
    cfg=safe_load(ymlFile)

urx='postgresql://' +cfg['datastore']['uid']+ ':' +cfg['datastore']['pwd']+ '@' +cfg['datastore']['host']+ ':' +str(cfg['datastore']['port'])+ '/' +cfg['datastore']['db']
P=Producer({'bootstrap.servers': cfg['kafka']['host']})

def dataSession():
	pgx=dbeng(urx)
	SessionClass=sessionmaker(bind=pgx)
	Session=SessionClass()
	return Session

def delivery_report(err,msg):
    if err is not None:
        print('Message delivery failed: {}'.format(err))
    else:
        print('Message delivered to {} [{}]'.format(msg.topic(), msg.partition()))

def queryParser(qList):
	nuList=[]
	qpSTR=" "
	for k,v in qList.items():
		if k.endswith('__between__'):
			kSTR=k[:-11]
			values2=v.split(',')
			qpSTR=qpSTR +kSTR+ " BETWEEN '" +values2[0]+ "' AND '" +values2[1]+ "' AND "
		else:
			qpSTR=qpSTR +k+ " LIKE '" +v+ "' AND "
	if qpSTR.endswith(" AND "):
		qpSTR=qpSTR[:-5]
	return qpSTR

def encode_dtm(obj):
    if isinstance(obj, dtm):
        return {'__datetime__': True, 'as_str': obj.strftime("%Y%m%dT%H:%M:%S")}
    return obj

def getTopic(eve='add'):
    if eve=='add':
        v_eve='topic-accounts-add'
    elif eve=='patch':
        v_eve='topic-accounts-patch'
    elif eve=='purge':
        v_eve='topic-accounts-purge'
    else:
        v_eve=False
    return v_eve

class getPostAcc(Resource):
	def get(self):
		jlist=[]
		qpm=request.args
		eventSession=dataSession()
		if len(qpm)==1:
			for k,v in qpm.items():
				col=k
				val=v
			if val.startswith('%') and val.endswith('%'):
				xClass=eventSession.query(A).filter(getattr(A,col).like('%%%s%%' % val))
			elif k.endswith('__between__'):
				xClass=eventSession.query(A).filter(alchemyText(queryParser(qpm))).all()
			else:
				xClass=eventSession.query(A).filter(getattr(A,col)==val)
		elif len(qpm)>1:
			xClass=eventSession.query(A).filter(alchemyText(queryParser(qpm))).all()
		else:
			xClass=eventSession.query(A).all()
		eventSession.close()
		for x in xClass:
			x.__dict__.pop('_sa_instance_state',None)
			jlist.append(x.__dict__)
		return jsonify(jlist)

	def post(self):
		if not request.get_json():
			abort(400)
		obo=request.get_json()
		thisTopic=getTopic()
		if isinstance(obo,list):
			etype='bulk'
		else:
			etype='one'
		eventDoc={'event':thisTopic,'action':etype,'etime':dtm.utcnow()}
		P.poll(0)
		P.produce(thisTopic,packb(obo,default=encode_dtm,use_bin_type=True),callback=delivery_report)
		P.produce('topic-events',packb(eventDoc,default=encode_dtm,use_bin_type=True),callback=delivery_report)
		return None

class AccountID(Resource):
	@jwt_required
	def get(self,accid):
		user=get_jwt_identity()
		print(user)
		if user!='nuPassword':
			return jsonify({'response':'Incorrect/Tampered Token'})
		print(user)
		eventSession=dataSession()
		xClass=eventSession.query(A).filter(A.aid==accid)
		eventSession.close()
		jlist=[]
		for x in xClass:
			x.__dict__.pop('_sa_instance_state',None)
			jlist.append(x.__dict__)
		return jsonify(jlist)
	def delete(self,accid):
        obo={'aid':accid,'active':False}
		thisTopic=getTopic('purge')
        eventDoc={'event':thisTopic,'action':'purge','etime':dtm.utcnow()}
        P.poll(0)
        P.produce(thisTopic,packb(obo,default=encode_dtm,use_bin_type=True),callback=delivery_report)
        P.produce('topic-events',packb(eventDoc,default=encode_dtm,use_bin_type=True),callback=delivery_report)
		return None
	def put(self,accid):
		obo=request.get_json()
        obo['aid']=accid
        thisTopic=getTopic('patch')
        eventDoc={'event':thisTopic,'action':'patch','etime':dtm.utcnow()}
        P.poll(0)
        P.produce(thisTopic,packb(obo,default=encode_dtm,use_bin_type=True),callback=delivery_report)
        P.produce('topic-events',packb(eventDoc,default=encode_dtm,use_bin_type=True),callback=delivery_report)
		return None

class getNewToken(Resource):
	def post(self):
		if not request.get_json():
			abort(400)
		obo=request.get_json()
		username=request.json.get('username',None)
		access_token=create_access_token(identity=username,expires_delta=tdt(seconds=cfg['app']['token']))
		return jsonify(access_token)
