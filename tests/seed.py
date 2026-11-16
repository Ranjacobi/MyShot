import json
inj = [("2026-10-08T09:05",2.5,"abd-r"),("2026-10-15T09:00",2.5,"abd-l"),("2026-10-22T08:50",2.5,"thigh-r"),("2026-10-29T09:20",2.5,"thigh-l"),("2026-11-05T09:00",5,"abd-r"),("2026-11-12T09:10",5,"abd-l")]
injections={"items":[{"id":f"i{n}","at":a,"dose":d,"site":s,"note":""} for n,(a,d,s) in enumerate(inj)]}
sym=[]
def S(at,t,s,h=None,n=""): sym.append({"id":f"s{len(sym)}","at":at,"t":t,"s":s,"h":h or [],"n":n})
for day in ["09","16","23","30"]:
    S(f"2026-10-{day}T13:00","nausea",2,["מנות קטנות"])
S("2026-10-10T08:00","constip",2,["יותר מים"])
S("2026-10-17T21:00","constip",3,["שזיפים או קיווי","הליכה"])
S("2026-11-06T12:30","nausea",3,["ג׳ינג׳ר","מנות קטנות"],"אחרי ארוחת צהריים כבדה")
S("2026-11-07T10:00","nausea",2,["מזון יבש ופשוט"])
S("2026-11-06T18:00","fatigue",2,["שתייה"])
S("2026-11-13T09:30","nausea",3,["ג׳ינג׳ר"])
S("2026-11-08T22:00","reflux",3,["ארוחה מוקדמת"])
S("2026-11-09T07:30","constip",2,["יותר מים","הליכה"])
symptoms={"items":sym}
weights={"items":[{"id":f"w{n}","d":d,"kg":k,"waist":None} for n,(d,k) in enumerate([("2026-10-08",98.2),("2026-10-15",97.1),("2026-10-22",96.5),("2026-10-29",95.6),("2026-11-05",94.8),("2026-11-12",94.1)])]}
weights["items"][-1]["waist"]=101
receipts={"items":[
 {"id":"r1","d":"2026-10-07","amt":1120,"v":"בית מרקחת הקופה","c":"mj","st":"paid","ref":560,"n":"עט 2.5 מ״ג","img":None},
 {"id":"r2","d":"2026-11-03","amt":1310,"v":"בית מרקחת הקופה","c":"mj","st":"sent","ref":0,"n":"","img":None},
 {"id":"r3","d":"2026-11-04","amt":45,"v":"פארם השכונה","c":"needles","st":"todo","ref":0,"n":"","img":None},
 {"id":"r4","d":"2026-11-10","amt":89.9,"v":"פארם השכונה","c":"supps","st":"none","ref":0,"n":"ויטמין D","img":None}]}
daily={"days":{"2026-11-12":{"w":7,"p":85,"s":{"sp1":1},"f":3,"bm":True,"walk":True,"str":False},"2026-11-13":{"w":3,"p":30,"s":{},"f":0,"bm":False,"walk":False,"str":False}}}
core={"settings":{"day":4,"time":"09:00","start":"2026-10-08","dose":5,"perPen":4,"arms":False,"water":8,"protein":90,"goalKg":85,"setup":True},"pen":{"opened":"2026-11-05","used":2,"spare":1},"supps":[{"id":"sp1","name":"ויטמין D"},{"id":"sp2","name":"ויטמין B12"}],"questions":[{"id":"q1","q":"האם לעלות ל-7.5 מ״ג בחודש הבא?","done":False},{"id":"q2","q":"מתי לעשות בדיקות דם?","done":True}]}
SEED={"core":core,"injections":injections,"symptoms":symptoms,"weights":weights,"receipts":receipts,"daily":daily}
