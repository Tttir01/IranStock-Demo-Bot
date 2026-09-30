def position_size(cash,price,max_position_pct=.20):
    return max(0,int((cash*max_position_pct)//price)) if price>0 else 0

def exit_reason(position,price):
    if price<=position.stop_loss:return "STOP_LOSS"
    if price>=position.take_profit:return "TAKE_PROFIT"
    return None
