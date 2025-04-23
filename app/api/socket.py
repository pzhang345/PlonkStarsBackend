from api.map.edit.socket import register_map_edit_socket
from api.party.socket import register_party_socket

def register_sockets(socketio):
    register_map_edit_socket(socketio,namespace="/socket/map/edit")
    register_party_socket(socketio,namespace="/socket/party")
   
    