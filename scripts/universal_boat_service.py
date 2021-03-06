#!/usr/bin/env python

# Title: Universal Boat
# Description: Boats will using clustering info and TSP solvers to travels to cluster locations quickly
# Engineer: Jonathan Lwowski 
# Email: jonathan.lwowski@gmail.com
# Lab: Autonomous Controls Lab, The University of Texas at San Antonio

#########          Libraries         ###################

import sys
from matplotlib import pyplot
from std_msgs.msg import String
import rospy
from std_msgs.msg import Empty,Bool
from geometry_msgs.msg import Twist 
from nav_msgs.msg import Odometry
from geometry_msgs.msg import PointStamped
from geometry_msgs.msg import Vector3Stamped
import math
import numpy as np
import time
import random
from geometry_msgs.msg import Pose
from geometry_msgs.msg import PoseArray
import os
import sys
from cooperative_mav_asv.msg import *

basepath = os.path.dirname(__file__)
filepath = os.path.abspath(os.path.join(basepath, "..", "tsp-solver"))
sys.path.append(filepath)

from tsp_solver.greedy import solve_tsp
from collections import defaultdict
from gazebo_msgs.msg import ModelStates
from std_srvs.srv import Empty
from cooperative_mav_asv.msg import *
from cooperative_mav_asv.srv import *

###### Global Variables   #####################
ugv_orientation_x=0
ugv_orientation_y=0
ugv_orientation_z=0
ugv_orientation_w=0
ugv_pose_x=0
ugv_pose_y=0
ugv_yaw=0
metacluster_location_array = []
boat_location = 0
boat_human_check = True
boat_capacity = 0
boat_speed = 0
auction_info = []
uavs_ready = False

##### Dijkstra Class  #######################
class Graph(object):
    def __init__(self):
        self.nodes = set()
        self.edges = defaultdict(list)
        self.distances = {}

    def add_node(self, value):
        self.nodes.add(value)

    def add_edge(self, from_node, to_node, distance):
        self.edges[from_node].append(to_node)
        self.edges[to_node].append(from_node)
        self.distances[(from_node, to_node)] = distance




##### UGV Nav Data Subscriber ###############
def ugvOdomCallback(data):
    global ugv_orientation_x
    global ugv_orientation_y
    global ugv_orientation_z
    global ugv_orientation_w
    global ugv_pose_x
    global ugv_pose_y
    ugv_pose_x = data.pose.pose.position.x
    ugv_pose_y = data.pose.pose.position.y
    ugv_orientation_x=data.pose.pose.orientation.x
    ugv_orientation_y=data.pose.pose.orientation.y
    ugv_orientation_z=data.pose.pose.orientation.z
    ugv_orientation_w=data.pose.pose.orientation.w
    e1=ugv_orientation_x
    e2=ugv_orientation_y
    e0=ugv_orientation_z
    e3=ugv_orientation_w
    #Heading
    global ugv_yaw
    ugv_yaw = math.atan2(2*(e0*e3+e1*e2),(e0**2+e1**2-e2**2-e3**2))
    ugv_yaw=ugv_yaw*180/math.pi

def ugvnav():
    rospy.Subscriber("odom", Odometry, ugvOdomCallback)    


##### People Location Subscriber ###############    
def metaclusterLocationCallback(data):
    global metacluster_location_array
    metacluster_location_array = data
    

def metacluster_location_sub():
    rospy.Subscriber("/metaclusters_locations", MetaClusters, metaclusterLocationCallback)   

def set_velocity_ugv(lx1, ly1, lz1, ax1, ay1, az1):   
	pub1 = rospy.Publisher('cmd_vel', Twist, queue_size=10)
	r = rospy.Rate(30) # 10hz
	command1 = Twist()
	command1.linear.x = lx1
	command1.linear.y = ly1
	command1.linear.z = lz1
	command1.angular.x = ax1
	command1.angular.y = ay1
	command1.angular.z = az1
    
	stop = Twist()
	stop.linear.x = 0
	stop.linear.y = 0
	stop.linear.z = 0
	stop.angular.x = 0
	stop.angular.y = 0
	stop.angular.z = 0
    
	if(boat_human_check == True):
		pub1.publish(command1)
	else:
		pub1.publish(stop)
      
def turn_direction(angle_init, ugv_angle):
   if(angle_init >= 0):
      angle_back = angle_init-180
   else:
      angle_back = angle_init+180
   if(angle_init >=0 and ugv_angle <= angle_init and ugv_angle >= angle_back):
      turn_sign = 1
   elif(angle_init >=0 and ((ugv_angle >= angle_init and ugv_angle <=180) or (ugv_angle <= angle_back))):
      turn_sign = -1
   elif(angle_init < 0 and ((ugv_angle <= angle_init and ugv_angle >=-180) or (ugv_angle >= angle_back))):
      turn_sign = 1
   elif(angle_init < 0 and ugv_angle > angle_init and ugv_angle < angle_back):
      turn_sign = -1
   return turn_sign 
 
def angle_difference(uav_angle, ugv_angle):
   if(uav_angle >=0 and ugv_angle >=0):
      diff=abs(uav_angle - ugv_angle)
   elif(uav_angle >=0 and ugv_angle <0):
      diff = abs(360-uav_angle-abs(ugv_angle))
   elif(uav_angle <0 and ugv_angle >=0):
      diff = abs( abs(uav_angle) + ugv_angle)
   elif(uav_angle <0 and ugv_angle < 0):
      diff = abs(uav_angle - ugv_angle)
   if(diff > 180):
      diff = abs(360-diff)
   return diff


def goto_target(x,y):
	D_yaw = 1   
	Derivator_yaw = 0
	error_yaw = 0;
	Kd_yaw = 1
	diff_x = abs(ugv_pose_x-x)
	diff_y = abs(ugv_pose_y-y)
	goal_x = x - ugv_pose_x
	goal_y = y - ugv_pose_y
	while (diff_x > .1 or diff_y>.1):
		angle = rotate_target(goal_x,goal_y)
		############# YAW PID   #####################
		diff_yaw = angle_difference(ugv_yaw,angle)
		sign_yaw = turn_direction(ugv_yaw, angle)
		P_yaw = sign_yaw*diff_yaw*.05
		error_yaw = diff_yaw
		D_yaw = Kd_yaw * (error_yaw - Derivator_yaw)
		PD_yaw = P_yaw + D_yaw
		Derivator_yaw= error_yaw
		Kd_yaw = D_yaw
		set_velocity_ugv(0.5,0,0,0,0,PD_yaw)
		diff_x = abs(ugv_pose_x-x)
		diff_y = abs(ugv_pose_y-y)
		goal_x = x - ugv_pose_x
		goal_y = y - ugv_pose_y
	set_velocity_ugv(0,0,0,0,0,0)
	return 1

def rotate_target(x,y):
   if(x<0 and y >0):
      angle = math.atan2(x, y) + math.pi/2
   if(x>0 and y>0):
      angle = math.atan2(x, y) + math.pi/2
   if(x<0 and y<0):
      angle = math.atan2(x, y)+ math.pi/2
   if(x>0 and y<0):      
      angle =  math.atan2(x, y) - (3*math.pi/2)
   if(x==0 and y>0):
      angle = math.pi/2
   if(x==0 and y<0):
      angle = -math.pi/2
   if(y==0 and x<0):
      angle = 0
   if(y==0 and x>0):
      angle = math.pi
   angle=angle*180/math.pi
   return angle

def distance(p0, p1):
    return math.sqrt((p0[0] - p1[0])**2 + (p0[1] - p1[1])**2)

def boatCallback(data):
	global boat_location
	location_array = []
	for i in range(len(data.name)):
		if "boat" in data.name[i]:
			boat_location = data.pose[i]

def boat_location_sub():
	rospy.Subscriber("/gazebo/model_states", ModelStates, boatCallback)

def uavsreadyCallback(data):
	global uavs_ready
	uavs_ready = data

def uavs_ready_sub():
	rospy.Subscriber("/uavs_done", Bool, uavsreadyCallback) 

def human_boat_check_Callback(data):
	global boat_human_check
	boat_human_check = data.data
	#print boat_human_check
	
def human_boat_check_sub():
	rospy.Subscriber("human_boat_check", Bool, human_boat_check_Callback)

def human_boat_check_pub():
	pub2 = rospy.Publisher('human_boat_check', Bool, queue_size=10)
	r = rospy.Rate(30) # 10hz
	command1 = True
	pub2.publish(command1)

def boat_auction__info_pub():
	global boat_speed
	global boat_capacity
	global boat_location
        pub2 = rospy.Publisher('boat_auction_info', BoatAuctionInfo, queue_size=10)
        r = rospy.Rate(30) # 10hz
        while(not isinstance(boat_location, Pose)):
		a=1
		#print "waiting"	

	command1 = BoatAuctionInfo()
	boat_name = rospy.get_namespace()

	command1.boat_name = boat_name.replace("/","")
	rospy.set_param('boat_name', boat_name.replace("/",""))

	command1.capacity = boat_capacity
	rospy.set_param('boat_capacity', boat_capacity)

	command1.speed = boat_speed 
	rospy.set_param('boat_speed', boat_speed)

	command1.pose = boat_location
	rospy.set_param('boat_location_x', boat_location.position.x)
	rospy.set_param('boat_location_y', boat_location.position.y)
	rospy.set_param('boat_location_z', boat_location.position.z)

	#print command1
        pub2.publish(command1)
	return command1

def auction_info_Callback(data):
	global auction_info
	auction_info = data

def auction_info_sub():
	rospy.Subscriber("/auction_assignments", AuctionAssignments, auction_info_Callback)

def get_relevant_clusters(auction_info,metacluster_location_array):
	clusters_assigned = []
	clusters_assigned_locations = []
	boat_name = rospy.get_namespace()
	boat_number = int(filter(str.isdigit, boat_name))-1
	#print boat_name
	#print ("boat number: ", boat_number)
	
	metacluster_assigned = auction_info.auction_assignments[boat_number]
	#print ("meta assigned: ", metacluster_assigned)
	if metacluster_location_array != []:
		for i in range(len(metacluster_location_array.metaclusters)):
			#print ("metacluster_location_array.metaclusters[i].label: ", metacluster_location_array.metaclusters[i].label)
			if int(metacluster_location_array.metaclusters[i].label) == metacluster_assigned:
				#print ("metacluster_location_array.metaclusters[i] ", metacluster_location_array.metaclusters[i])
				clusters_assigned=metacluster_location_array.metaclusters[i]
	if( clusters_assigned != [] ):
		for i in range(len(clusters_assigned.clusters.clusters)):
			clusters_assigned_locations.append(clusters_assigned.clusters.clusters[i].pose)
	#print clusters_assigned_locations
				
	return clusters_assigned_locations

def setup_tsp(people_location_array):
	graph_people_locations = Graph()
	number = 1
	people_location_array_current = people_location_array
	#print people_location_array_current				
	w, h = len(people_location_array_current)+1, len(people_location_array_current)+1
	cost_mat = [[0 for x in range(w)] for y in range(h)] 
	graph_people_locations.add_node(str(0))
	for i in range(len(people_location_array_current)):
		graph_people_locations.add_node(str(number))
		number = number + 1
	for node in graph_people_locations.nodes:
		for node2 in graph_people_locations.nodes:
			if(node != '0' and node2 != '0'):
				cost = distance((people_location_array_current[int(node)-1].position.x, people_location_array_current[int(node)-1].position.y),
					(people_location_array_current[int(node2)-1].position.x,
					people_location_array_current[int(node2)-1].position.y))
			else:
				cost = 9999999
			graph_people_locations.add_edge(node,node2,cost)
			cost_mat[int(node)][int(node2)]=cost
	return cost_mat

def travel_using_tsp(path, people_location_array_current):
	for locs in path:
		if(path[locs] != 0):
			print ("Going to location: (", people_location_array_current[locs-1].position.x, ",",
				people_location_array_current[locs-1].position.y,")")
			goto_target(people_location_array_current[locs-1].position.x,
				people_location_array_current[locs-1].position.y)

def call_metaclustering_service_client():
	print "meta srv"
	rospy.wait_for_service('/metaclustering')
	try:
		metaclusters_service = rospy.ServiceProxy('/metaclustering',MetaClustering)
		metaclusters_service_response  = metaclusters_service()
		return metaclusters_service_response
	except rospy.ServiceException, e:
        	print "Service call failed: %s"%e


def call_auctioning_service_client():
	print "auction srv"
	rospy.wait_for_service('/auctioning')


	try:
		auction_service = rospy.ServiceProxy('/auctioning',Auctioning)
		auction_service_response  = auction_service()
		return auction_service_response
	except rospy.ServiceException, e:
        	print "Service call failed: %s"%e

def handle_startboats(arg=0):
	
	global boat_speed
	global boat_capacity
	boat_speed = random.uniform(.2,1.0)
	boat_capacity = random.uniform(10,150)

	rospy.Rate(30)
	human_boat_check_sub()
        boat_location_sub()

	human_boat_check_pub()
	command = boat_auction__info_pub()
	ugvnav()
	time.sleep(2)
	resp = call_auctioning_service_client()
	metacluster_location_array = resp.metaclusters
	auction_info = resp.auction_assignments

	print "before if", auction_info, metacluster_location_array
	if ((metacluster_location_array != []) and (auction_info != [])):
		print "entered if"
		assigned_clusters_locations = get_relevant_clusters(auction_info,metacluster_location_array)
		print "got assigned clusters"
		cost_mat = setup_tsp(assigned_clusters_locations)
		print "got cost mat"
		path = solve_tsp( cost_mat )
		print "solved tsp"
		travel_using_tsp(path,assigned_clusters_locations)
		print "after travling"

	return True

def start_boats_service():
	rospy.init_node('start_boats_service', anonymous=True)
	print "Starting the boat"
	rospy.Service('start_boats', StartBoats, handle_startboats)
	print "Successfully started the boat"
	rospy.spin()
	handle_startboats()	

if __name__ == '__main__':
	start_boats_service()
