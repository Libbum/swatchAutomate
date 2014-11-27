var data = {"start":Date.now()-30000,"end":Date.now(),"step":3000,"names":["UpStream","DownStream"],"values":[[300, 350, 200, 210, 300, 450, 240, 200, 320, 400],[200, 320, 400, 310, 380, 410, 340, 200, 320, 400]]};

/*
 * delta updates to data that would be incrementally appended to the original every 1 second (1000ms)
 */
var dataA = {"start":Date.now()+11000,"end":Date.now()+11000,"step":1000,"names":["UpStream","DownStream"],"values":[[250],[350]]};
