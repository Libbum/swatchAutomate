/* Socket controlling functions */

/* The sockets adress will be updated to it's correct location after testing */
var ws = new WebSocket("ws://192.168.1.103:8888/websocket");

ws.onmessage = function(evt){
    /* Debug log, may be removed in a future version */
    ix = document.createElement("p");
    ix.innerHTML = evt.data;
    document.getElementById("console").appendChild(ix);

    /* Checx to see if an additional command has been sent */
    var cmd = evt.data.split("&");
    var type = 0;
    if (cmd.length > 1) {
        /* This may also be useful for ACK*/
        if (cmd[1] === "1") {
            /* Startup */
            type = 2;
        }
        data.push({"x" : 4,"y" : 2});
        redraw();
    }
}
   
function DispatchResponse(){
    /* A debugging function to take the command written in the console and push it through the web socket */
    var userInput = document.getElementById("message").value;
    document.getElementById("message").value = "";
    ix = document.createElement("p");
    ix.innerHTML = "You sent: " + userInput;
    document.getElementById("console").appendChild(ix);
    ws.send(userInput);
}