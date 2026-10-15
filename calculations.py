import math

class Calc:
    @staticmethod
    def brick(length, width, height):
        perimeter = 2 * (length + width)
        wall_area = perimeter * height
        net = wall_area * 0.80
        bpm2 = 2 * 10000 / ((21+1.5)*(6.5+1.5))
        total = math.ceil(net * bpm2)
        waste = math.ceil(total * 1.05)
        mv = net * 0.22 * 0.25
        return {"wall_area": round(wall_area,2), "net": round(net,2),
                "bpm2": round(bpm2), "total": total, "waste": waste,
                "cement_bags": math.ceil(mv*350/50), "sand_tons": round(mv*1.5,2)}

    @staticmethod
    def concrete(length, width, thickness):
        v = length * width * thickness
        vw = v * 1.10
        return {"volume": round(v,3), "volume_waste": round(vw,3),
                "cement_kg": round(vw*350), "cement_bags": math.ceil(vw*350/50),
                "sand_kg": round(vw*700), "gravel_kg": round(vw*1100),
                "water_l": round(vw*175)}

    @staticmethod
    def rebar(area, thickness=0.2):
        v = area * thickness
        r = v * 80
        return {"volume": round(v,3), "rebar_kg": round(r),
                "rebar_waste": round(r*1.05)}

    @staticmethod
    def paint(area, coats=2):
        p = (area * coats) / 10
        pw = p * 1.10
        return {"liters": round(p,1), "waste_liters": round(pw,1),
                "gallon_4l": math.ceil(pw/4), "bucket_20l": math.ceil(pw/20)}

    @staticmethod
    def cement(area, thickness=0.03):
        v = area * thickness
        ck = v * 400
        return {"volume": round(v,3), "cement_kg": round(ck),
                "cement_bags": math.ceil(ck/50), "sand_tons": round(v*1.5,2)}

    @staticmethod
    def tile(length, width):
        a = length * width
        tn = a / 0.16
        tw = math.ceil(tn * 1.10)
        return {"area": round(a,2), "tiles": math.ceil(tn),
                "tiles_waste": tw, "adhesive_kg": round(a*5),
                "adhesive_bags": math.ceil(a*5/25)}

    @staticmethod
    def gypsum(area):
        v = area * 0.02
        gk = v * 1000
        return {"volume": round(v,3), "gypsum_kg": round(gk),
                "gypsum_bags": math.ceil(gk/40)}

    @staticmethod
    def waterproof(area):
        ta = area * 2
        return {"total_area": round(ta,2),
                "rolls": math.ceil(ta/10*1.15),
                "primer_l": round(area*0.3,1)}

    @staticmethod
    def foundation(length, width, depth):
        v = length * width * depth
        rk = v * 110
        c = Calc.concrete(length, width, depth)
        return {"volume": round(v,3), "rebar_kg": round(rk),
                "rebar_waste": round(rk*1.05),
                "cement_bags": c["cement_bags"],
                "sand_kg": c["sand_kg"], "gravel_kg": c["gravel_kg"]}

    @staticmethod
    def column(w, d, h, rc=8, rd=16):
        v = w * d * h
        ra = math.pi * (rd/2000)**2
        mr = rc * h * 1.05 * ra * 7850
        sp = 2*(w+d-0.08)
        sc = math.ceil(h/0.15)+1
        sa = math.pi*(8/2000)**2
        sw = sc * sp * sa * 7850
        tr = mr + sw
        c = Calc.concrete(w, d, h)
        return {"volume": round(v,4), "main_rebar": round(mr,1),
                "stirrup_kg": round(sw,1), "stirrup_count": sc,
                "total_rebar": round(tr,1), "cement_bags": c["cement_bags"],
                "concrete_vol": c["volume_waste"]}

    @staticmethod
    def estimate(area, floors, structure, quality):
        costs = {
            "steel": {"economic":15000000,"medium":22000000,"luxury":35000000},
            "concrete": {"economic":16000000,"medium":23000000,"luxury":37000000},
            "masonry": {"economic":12000000,"medium":18000000,"luxury":28000000},
        }
        cpm = costs.get(structure, costs["concrete"]).get(quality, 23000000)
        ta = area * floors
        tc = ta * cpm
        bd = {
            "🏗 اسکلت": round(tc*0.30),
            "🏗 فونداسیون": round(tc*0.10),
            "🧱 دیوارچینی": round(tc*0.10),
            "🎨 نازک‌کاری": round(tc*0.20),
            "🔧 مکانیکی": round(tc*0.12),
            "⚡ برقی": round(tc*0.08),
            "📋 متفرقه": round(tc*0.10),
        }
        return {"total_area": ta, "cost_per_m2": cpm,
                "total_cost": round(tc), "breakdown": bd}

def fmt(n):
    if isinstance(n, float): n = round(n)
    return "{:,}".format(int(n))

def fmtp(p):
    if p >= 1e9: return f"{p/1e9:.1f} میلیارد تومان"
    if p >= 1e6: return f"{p/1e6:.1f} میلیون تومان"
    return f"{fmt(p)} تومان"
