from flask import Flask, request, jsonify
from flask_cors import CORS

import os, sys
from os import environ

import requests
from invoke import invoke_http

import amqp_setup
import pika
import json

app = Flask(__name__)
CORS(app)

restaurant_URL = "http://localhost:5005/restaurant" or environ.get("restaurant_URL")
order_URL = "http://localhost:5002/order" or environ.get("order_URL")
rider_URL = "http://localhost:5001/rider" or environ.get("rider_URL")
activity_log_URL = "http://localhost:5003/activity_log" or environ.get("activity_log_URL")
error_URL = "http://localhost:5004/error" or environ.get("error_URL")


@app.route("/place_order", methods=['POST'])
def place_order():
    # Simple check of input format and data of the request are JSON
    if request.is_json:
        try:
            order = request.get_json()
            print("\nReceived an order in JSON:", order)

            # do the actual work
            # 1. Send order info {cart items}
            result = processPlaceOrder(order)
            print("'\n------------------------")
            print("\nresult: ", result)
            return jsonify(result), result["code"]

        except Exception as e:
            # Unexpected error in code
            exc_type, exc_obj, exc_tb = sys.exc_info()
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            ex_str = str(e) + " at " + str(exc_type) + ": " + fname + ": line " + str(exc_tb.tb_lineno)
            print(ex_str)

            return jsonify({
                "code": 500,
                "message": "place_order.py internal error: " + ex_str
            }), 500

    # if reached here, not a JSON request.
    return jsonify({
        "code": 400,
        "message": "Invalid JSON input: " + str(request.get_data())
    }), 400


def processPlaceOrder(order):
    # 2. Send the order info {cart items}
    # Invoke the order microservice
    print("\n-----Invoking order microservice-----")
    order_result = invoke_http("http://localhost:5002/order", method="POST", json=order)
    print("order_result:", order_result)

    # Check the order result; if a failure, send it to the error microservice
    code = order_result["code"]
    message = json.dumps(order_result)

    amqp_setup.check_setup()

    if code not in range(200,300):
         # Inform the error microservice
        #print('\n\n-----Invoking error microservice as order fails-----')
        print('\n\n-----Publishing the (order error) message with routing_key=order.error-----')

        # invoke_http(error_URL, method="POST", json=order_result)
        amqp_setup.channel.basic_publish(exchange=amqp_setup.exchangename, routing_key="order.error", 
            body=message, properties=pika.BasicProperties(delivery_mode = 2)) 
        # make message persistent within the matching queues until it is received by some receiver 
        # (the matching queues have to exist and be durable and bound to the exchange)

        # - reply from the invocation is not used;
        # continue even if this invocation fails        
        print("\nOrder status ({:d}) published to the RabbitMQ Exchange:".format(
            code), order_result)

        # 7. Return error
        return {
            "code": 500,
            "data": {"order_result": order_result},
            "message": "Order creation failure sent for error handling."
        }
    
    # Notice that we are publishing to "Activity Log" only when there is no error in order creation.
    # In http version, we first invoked "Activity Log" and then checked for error.
    # Since the "Activity Log" binds to the queue using '#' => any routing_key would be matched 
    # and a message sent to “Error” queue can be received by “Activity Log” too.

    else:
        # 4. Record new order
        # record the activity log anyway
        #print('\n\n-----Invoking activity_log microservice-----')
        print('\n\n-----Publishing the (order info) message with routing_key=order.info-----')        

        # invoke_http(activity_log_URL, method="POST", json=order_result)            
        amqp_setup.channel.basic_publish(exchange=amqp_setup.exchangename, routing_key="order.info", 
            body=message)
    
    print("\nOrder published to RabbitMQ Exchange.\n")
    # 4. Record new order
    # record the activity log anyway
    # print("\n\n-----Invoking activity_log microservice-----")
    # invoke_http(activity_log_URL, method="POST", json=order_result)
    # print("\nnOrder sent to activity log. \n")
    #- reply from the invocation is not used;
    # continue even if this invocation fails
    # Check the order result; if a failure, send it to the error microservice.
    # code = order_result["code"]
    # if code not in range(200,300):
    #     # Inform the error microservice
    #     print("\n\n-----Invoking error microservice as order fails-----")
    #     invoke_http(error_URL, method="POST", json=order_result)
    #     #- reply from the invocation is not used;
    #     #continue even if this invocation fails
    #     print("Order status ({:d}) sent to the error microservice:".format(code), order_result)
    #     # 7. Return error
    #     return {
    #         "code" : 500,
    #         "data" : {"order_result" : order_result},
    #         "message" : "Order creation failure sent for error handling"
    #     }
    # else: print("\n\nOrder Successfully Placed\n")

    # 5. Send new order to shipping
    # Invoke the shipping record microservice

    # Check the shipping result;
    # if a failure, send it to the error microservice.

    # Inform the error microservice

    # 7. Return error

    # 7. Return created order, shipping record
    return {
        "code" : 201,
        "data" : {
            "order_result" : order_result
        },
        "message" : "Order Succesfully Placed"
    }


# Execute this program if it is run as a main script (not by 'import')
if __name__ == "__main__":
    print("This is flask " + os.path.basename(__file__) +
          " for placing an order...")
    app.run(host="0.0.0.0", port=5100, debug=True)
    # Notes for the parameters:
    # - debug=True will reload the program automatically if a change is detected;
    #   -- it in fact starts two instances of the same flask program,
    #       and uses one of the instances to monitor the program changes;
    # - host="0.0.0.0" allows the flask program to accept requests sent from any IP/host (in addition to localhost),
    #   -- i.e., it gives permissions to hosts with any IP to access the flask program,
    #   -- as long as the hosts can already reach the machine running the flask program along the network;
    #   -- it doesn't mean to use http://0.0.0.0 to access the flask program.
